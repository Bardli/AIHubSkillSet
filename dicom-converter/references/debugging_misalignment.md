# Debugging Label Misalignment

When labels look "shifted by a couple slices" or are wildly off, work through these checks in order. Each is a few lines of code and rules out (or confirms) a specific failure mode.

## Check 1 — HU values at label voxels

Sanity-check that the labelled voxels look like the tissue they're supposed to. Air or bone at "liver" label is a smoking gun.

```python
import nibabel as nib
import numpy as np

img_data = nib.load(img_path).get_fdata()
lbl_data = nib.load(lbl_path).get_fdata()

if (lbl_data > 0).any():
    hu_at_label = img_data[lbl_data > 0].mean()
    print(f"Mean HU at label: {hu_at_label:.1f}")
```

Expected ranges (CT, abdomen window):

| Tissue | HU range |
|---|---|
| Liver, kidney, pancreas, spleen | 40 – 100 |
| Lung tumor (soft tissue lesion) | -50 – 50 |
| Bone | +1000 |
| Air / lung parenchyma | -1000 |

If your "soft tissue" label is centred around -1000 HU, the mask is in the air around the patient — almost always a slice-routing bug or a wrong reference image.

## Check 2 — Z-spacing uniformity

Non-uniform z is the single most common reason for "off by a couple slices" symptoms.

```python
import pydicom
import numpy as np

zs = sorted([
    float(pydicom.dcmread(f, stop_before_pixels=True).ImagePositionPatient[2])
    for f in dcm_files
])
spacings = np.diff(zs)
print(f"Min/median/max gap: {spacings.min():.3f} / {np.median(spacings):.3f} / {spacings.max():.3f} mm")
print(f"Stdev: {np.std(spacings):.3f} mm  (>0.1 → NON-UNIFORM, SimpleITK grid is wrong)")
```

If non-uniform, the cure is SOP-UID routing for slice assignment (see `sop_uid_routing.md`) and using actual z-positions for polygon rasterization (see `image_stack_traps.md`).

## Check 3 — Multi-acquisition under one series

```python
acq_numbers = {
    int(getattr(pydicom.dcmread(f, stop_before_pixels=True), "AcquisitionNumber", 1))
    for f in dcm_files
}
if len(acq_numbers) > 1:
    print(f"Multi-acquisition: {sorted(acq_numbers)} — split before stacking")
```

If multi-acq and you're still using `sitk.ImageSeriesReader` over the whole series, the image volume itself is wrong (cross-phase blending). Split by `AcquisitionNumber` first.

## Check 4 — Multi-RTSTRUCT in annotation directory

```python
from pathlib import Path
rtstruct_files = [
    f for f in sorted(Path(annotation_dir).glob("*.dcm"))
    if pydicom.dcmread(str(f), stop_before_pixels=True).Modality == "RTSTRUCT"
]
print(f"RTSTRUCT files: {len(rtstruct_files)}")
```

If `>1`, you're under-counting voxels by reading only the first file. See `multi_rtstruct.md`. The bundled `scripts/parse_rtstruct_union.py` ORs all of them.

## Check 5 — Did you trust `SliceThickness` or `SpacingBetweenSlices`?

Both tags lie. Recompute spacing from `ImagePositionPatient` differences:

```python
spacing_from_tag = float(pydicom.dcmread(dcm_files[0], stop_before_pixels=True).SliceThickness)
spacing_from_ipp = float(np.median(np.diff(sorted(zs))))
print(f"SliceThickness tag: {spacing_from_tag} mm  vs IPP-derived median: {spacing_from_ipp:.3f} mm")
```

If they disagree by more than 0.5 mm, the tag is wrong. Use the IPP-derived value everywhere.

## Common mistakes (summary)

| Mistake | Consequence | Fix |
|---|---|---|
| Route contours/frames to acquisitions by z-coordinate geometry | Cross-acq leakage, "outside-z-range" rejections, off-by-one slices on shared-z, mask shifts under non-uniform z | `sop_uid_routing.md`: route by `ContourImageSequence` / `DerivationImageSequence` SOP UID. Nearest-z is fallback ONLY when UID absent. |
| `parse_rtstruct(dcm_files[0])` — read only the first RTSTRUCT | N-1 ROIs silently dropped (measured 10× undercount, 13,929 vs 145,642 voxels) | `multi_rtstruct.md`: iterate every `*.dcm`, filter `Modality == "RTSTRUCT"`, union ROIs. |
| Z-dedup the CT stack and prune the `sop_to_acq` map together | Duplicate-z slices fall back to nearest-z and leak contours into the wrong acq | `image_stack_traps.md`: build `sop_to_acq` from the full file list; dedup only the image stack. |
| Clamp/reject out-of-range contours by z | Massive spurious label on slice 0 (legacy V3 path) | Use SOP UID — there is no "out of range", the contour is anchored to a real slice. |
| Fix RTSTRUCT routing but leave SEG using `_belongs_to_acq` | SEG labels still mis-routed on shared-z and merged multi-acq series | Mirror `sop_uid_routing.md` in `convert_seg_to_mask` via `DerivationImageSequence[0].SourceImageSequence[0].ReferencedSOPInstanceUID` per frame. |
| Trust `SpacingBetweenSlices` / `SliceThickness` tag | Wrong z-spacing (can be 0.0) | Compute from IPP differences. |
| Trust `TransformPhysicalPointToContinuousIndex` for z | Wrong slice for non-uniform z-spacing | Check uniformity first; use actual DICOM z-positions if non-uniform. |
| Manual pydicom SEG decoding when `sitk.ReadImage` works | Bugs from hand-built geometry (direction matrix transposition, wrong z-spacing) | Try `sitk.ReadImage(seg_path)` first — see `seg_decoding.md`. |
| Apply EAY131 CT workarounds to all DICOM data | Unnecessary complexity, new bugs | Audit each dataset (see `audit_checklist.md`) before adding workarounds. |
| `Path.stem` on `.nii.gz` files | Returns `file.nii` not `file` | `name.replace('.nii.gz', '')`. |
| Use `--patient` mode for partial reconversion | CT numbering changes | Full reconversion or targeted label-only fix. |
| Overwrite `metadata.csv` in `--patient` mode | Lose all other patients' metadata | Merge new rows into existing CSV. |
| Docker with symlinked input dirs | Files not found inside container | Mount real directories. |
| One CT window for all body parts | Lung lesions invisible | Per-subfolder windowing — see `downstream_stages.md`. |
