# DICOM Audit Checklist (Clean vs Dirty)

A 30-second header-only audit decides whether the simple `sitk.ImageSeriesReader` path is safe or whether you must route through a metadata-first (V6-style) pipeline. Cheap to run (`pydicom.dcmread(stop_before_pixels=True)`), expensive to skip — corrupted NIfTI silently propagates downstream.

**Don't assume clinical data is clean.** Even well-known research collections occasionally have non-uniform z, multi-acquisition under one SeriesUID, or RTSTRUCTs missing the `ContourImageSequence` anchor.

## The 10 checks (any single red flag → dirty)

| # | Check | Trigger condition | Why it matters |
|---|---|---|---|
| 1 | Z-spacing uniformity | `np.std(np.diff(sorted(z))) > 0.01 mm` | SimpleITK forces a uniform grid; non-uniform → wrong z-indices in any geometric lookup. |
| 2 | Multi-acquisition under one SeriesUID | `len(set(AcquisitionNumber)) > 1` | `ImageSeriesReader` merges acquisitions into one volume; HU jumps + cross-phase blending. |
| 3 | Duplicate z-positions | `len(z) != len(set(z))` | Same physical z has multiple slices (overlapping recon or multi-acq); SimpleITK spacing breaks. |
| 4 | Orientation consistency | `ImageOrientationPatient` deviates from `[1,0,0,0,1,0]` or varies across slices | Coronal/sagittal/tilted → z ≠ IPP[2]; downstream code assuming axial is wrong. |
| 5 | Annotation anchoring | RTSTRUCT contour missing `ContourImageSequence`, or SEG frame missing `DerivationImageSequence.SourceImageSequence` | No SOP UID → forced into fragile nearest-z fallback. EAY131 V6 fallback rate is ~0.8% of contours, 0% of SEG frames; higher = data is dirty. |
| 6 | Multi-RTSTRUCT in annotation dir | `>1` `*.dcm` with `Modality=='RTSTRUCT'` | Reading only `dcm_files[0]` drops N-1 ROIs (10× undercount measured on EAY131-8365856 acq2). |
| 7 | Modality mixing in input dir | More than one `Modality` in same folder | RTSTRUCT/SEG mixed with CT confuses `ImageSeriesReader`; separate before conversion. |
| 8 | `SliceThickness` vs computed z-gap | `abs(SliceThickness - median(diff(z))) > 0.5 mm` | Tag and reality disagree — never trust the `SliceThickness` tag for spacing. |
| 9 | Localizer/scout mixed in | Any file with `'LOCALIZER'` in `ImageType` | 1–3 single-frame scouts pollute the volume; must be filtered. |
| 10 | RTSTRUCT FrameOfReferenceUID linkage | RTSTRUCT `ReferencedFrameOfReferenceSequence[0].FrameOfReferenceUID` ∉ {CT FoR UIDs} | Annotation references a different study/scan than the CT in the directory. |

## Decision rule

```
all green  →  use the simple converter (sitk.ImageSeriesReader, single pass)
any red    →  use the metadata-first pipeline (per-acq split, sop_to_acq, SOP-UID routing)
hard error →  fail loudly; do not silently produce a corrupted NIfTI
```

The bundled auditor `scripts/audit_dicom_dataset.py` runs all 10 checks header-only, exits `0` clean or `1` dirty, and can emit a CSV report. Use it to gate any new dataset before deciding which converter to run.

## Cleanliness reference points

| Dataset | Health | Recommended converter |
|---|---|---|
| MSD, BraTS, KiTS, AMOS challenges | Clean — uniform z, axial, single-acq | Simple `sitk.ImageSeriesReader` |
| PROSTATEx-Seg-HiRes (T2 MRI) | Mostly clean — uniform spacing, single-acq SEG | `sitk.ReadImage` direct (see `seg_decoding.md`) |
| EAY131 (NSCLC trial CT) | Dirty — 84% non-uniform z, 46%+ duplicate z, frequent multi-acq, 59 interleaved series | Metadata-first pipeline (V6) — see `sop_uid_routing.md`, `multi_rtstruct.md`, `image_stack_traps.md` |

## What to do when checks flip

- Check 1 (non-uniform z): see `image_stack_traps.md` and `seg_decoding.md`. Use real DICOM z-positions for lookups; `sitk.ReadImage` may still be safe for SEG if the SEG itself is uniformly framed.
- Check 2/3 (multi-acq, duplicate z): see `image_stack_traps.md`. Split by `AcquisitionNumber` *before* stacking.
- Check 5 (missing SOP UID anchor): expected for some legacy data. Track the fallback rate; >1% means the data is unusually dirty.
- Check 6 (multi-RTSTRUCT): see `multi_rtstruct.md`. Iterate every `*.dcm` and OR-union the ROIs.
- Check 8 (`SliceThickness` mismatch): never trust the tag. Compute spacing from IPP differences.
- Check 9 (localizer): filter by `'LOCALIZER' not in ds.ImageType` before stacking.
- Check 10 (FoR mismatch): refuse to convert; ask the user to provide the correct CT directory.
