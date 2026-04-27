# Image-Stack Traps (Multi-Acq, Duplicate Z, Non-Uniform Z, Orientation)

The geometric traps in DICOM CT/MR series. SOP-UID routing (see `sop_uid_routing.md`) handles annotation slice-assignment cleanly — these traps still apply when you have to *stack the image data itself* into a NIfTI volume.

## 1. Multi-acquisition under one SeriesUID

One series UID can contain 2 or 3 scan passes (different contrast phases, breath-holds, etc.). `sitk.ImageSeriesReader` blindly merges them into one volume — HU jumps and cross-phase blending are guaranteed.

**Detect:** `len(set(ds.AcquisitionNumber for ds in headers)) > 1`. The bundled `scripts/audit_dicom_dataset.py` flags this as check #2.

**Handle:** split files by `AcquisitionNumber` *before* stacking. Convert each acquisition to its own NIfTI. Keep an `acq{N}` suffix on the case ID (see `eay131_benchmark.md` for naming conventions).

```python
from collections import defaultdict

acqs = defaultdict(list)
for ds, path in zip(headers, paths):
    acqs[int(getattr(ds, "AcquisitionNumber", 1))].append(path)

# Now run sitk.ImageSeriesReader(...) once per acq, not once for the whole dir.
```

## 2. Duplicate z-positions

Same physical z, multiple files (overlapping reconstructions, multi-acquisition under one series). 46%+ of EAY131 CT series have duplicates. SimpleITK's spacing computation breaks if the z list has duplicates.

**Detect:** `len(zs) != len(set(zs))` after extracting `ImagePositionPatient[2]` from each header. Audit check #3.

**Handle:**
- **Dedup the image stack** before passing to `ImageSeriesReader` (or even before that — work out which file at each z to keep, e.g. by `InstanceNumber` or by recon kernel).
- **DO NOT prune `sop_to_acq`** when you dedup. Build the SOP-UID map from the *full* per-acquisition file list. A z-dedup that prunes the map re-introduces nearest-z fallback for any duplicate-z slice and silently leaks contours back into the wrong acquisition (EAY131 V6 dedup bug, patched 2026-04-26).

## 3. Non-uniform z-spacing

Common in CT (84% of EAY131 series). SimpleITK forces a uniform grid — `TransformPhysicalPointToContinuousIndex()` returns the **wrong z-index** when the underlying spacing is non-uniform.

**Detect:**
```python
import numpy as np
zs = sorted(z_positions_from_headers)
spacings = np.diff(zs)
is_uniform = np.std(spacings) < 0.1   # mm; True → SimpleITK is safe
```

Audit check #1 uses `> 0.01 mm` for the dirty threshold; the runtime sanity check above uses `< 0.1 mm` to decide whether to take the simple SEG path (see `seg_decoding.md`).

**Handle:**
- **For slice assignment** of annotations: route by SOP UID (see `sop_uid_routing.md`), not by z geometry. The non-uniformity becomes irrelevant.
- **For polygon rasterization onto its anchored slice:** you still need real z-positions to draw the polygon. Use the actual DICOM z-positions, not a `TransformPhysicalPointToContinuousIndex` result.
- **MRI sanity check first.** Most MRI is uniform, and the workarounds add bugs of their own (see PROSTATEx lesson in `seg_decoding.md`). Try simple first; escalate only when audit check #1 trips.

## 4. Non-axial orientation

40% of EAY131 series are coronal or sagittal. Don't assume `z = ImagePositionPatient[2]` — check `ImageOrientationPatient`.

**Detect:** `ImageOrientationPatient` deviating from `[1, 0, 0, 0, 1, 0]` or varying across slices. Audit check #4.

**Handle:** read the orientation, rotate the volume into the canonical axial frame *before* applying any code that assumes axial. Most of the time, the entire dataset is one orientation per series, so a single rotation per series is enough. Mixed orientation within a series is a hard error.

## 5. `SliceThickness` tag vs reality

The `SliceThickness` DICOM tag is frequently wrong (or 0.0). Compute spacing from `ImagePositionPatient` differences instead.

**Detect:** `abs(SliceThickness - median(diff(z))) > 0.5 mm`. Audit check #8.

**Handle:** never trust `SliceThickness`. Always compute spacing from IPP differences. Same applies to `SpacingBetweenSlices`.

## 6. Localizer / scout images mixed in

CT acquisitions often include 1–3 single-frame localizer/scout images in the series. They pollute the volume if not filtered.

**Detect:** any file with `'LOCALIZER' in ds.ImageType`. Audit check #9.

**Handle:** filter these out before stacking. Check on a single tag: `ds.ImageType` is a multi-valued string; localizers contain `'LOCALIZER'`. Some scouts also have `'OTHER'`; the localizer flag is the most reliable.

## 7. RTSTRUCT FrameOfReferenceUID mismatch

The RTSTRUCT references a different scan than the CT in the directory. Audit check #10. Refuse to convert; the user should provide the correct CT directory or you will silently apply contours to the wrong scan.

## Putting them together — the metadata-first flow

```
1. Load CT headers (header-only). Filter localizers. Group by AcquisitionNumber.
2. Per acquisition:
     a. Sort by z.
     b. Build sop_to_acq from the full file list (no dedup yet).
     c. Dedup the IMAGE stack only (keep one slice per z). Do not modify sop_to_acq.
     d. Compute spacing from IPP diffs (do not trust SliceThickness).
     e. Stack into a NIfTI.
3. Annotations:
     a. Iterate every *.dcm in the annotation dir; OR-union ROIs. (multi_rtstruct.md)
     b. For every contour/frame, capture the SOP UID anchor.
     c. Route by SOP UID; nearest-z is fallback only.
     d. Rasterize onto the anchored slice using actual z-positions.
4. Audit telemetry (route_sop_keep / route_nz_keep / route_sop_skip per acq) goes
   to a sidecar metadata.csv so you can detect regressions.
```
