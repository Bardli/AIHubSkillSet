# DICOM SEG Decoding (Simple SimpleITK vs Manual pydicom)

**Start simple, escalate only when needed.** The geometric traps in `image_stack_traps.md` are real but not universal. Check whether they actually apply to your data before adding workarounds — every workaround you add is another bug surface.

## Decision tree

```
Is z-spacing uniform?
  ├── YES (most MRI, some CT)  →  sitk.ReadImage(seg_path) works.
  │     Is SEG at the same resolution as the reference image?
  │       ├── YES → map frames directly to ref image slices.
  │       └── NO  → sitk.ReadImage + sitk.Resample(nearest-neighbor) to ref space.
  └── NO (EAY131 CT, many clinical CT)  →  manual pydicom frame decoding.
        Extract actual z-positions, use np.argmin nearest-neighbour lookup.
        Do NOT use sitk.Resample or TransformPhysicalPointToContinuousIndex for z.
        Mirror the SOP-UID routing from sop_uid_routing.md per frame.
```

## How to check z-spacing uniformity

Header-only — runs in seconds even on large series:

```python
import numpy as np
import pydicom

zs = sorted([
    float(pydicom.dcmread(f, stop_before_pixels=True).ImagePositionPatient[2])
    for f in dcm_files
])
spacings = np.diff(zs)
is_uniform = np.std(spacings) < 0.1   # True → SimpleITK is safe
```

`< 0.1 mm` is a runtime safety threshold. If you want to flag *any* non-uniformity for an audit report, use `< 0.01 mm` (audit check #1 in `audit_checklist.md`). The two thresholds reflect different goals: one decides "should I take the simple path" (ship a working pipeline), the other says "is this dataset clean" (catalogue the data).

## The simple path (uniform spacing)

```python
import SimpleITK as sitk

ref = sitk.ReadImage(image_nifti_or_first_dicom)   # establishes geometry
seg = sitk.ReadImage(seg_dicom_path)               # SimpleITK reads SEG natively

# Same resolution → just align spatial metadata
if seg.GetSize() == ref.GetSize() and seg.GetSpacing() == ref.GetSpacing():
    mask_arr = sitk.GetArrayFromImage(seg)         # shape (Z, Y, X)
else:
    # Different resolution → resample to ref space, NEAREST for masks
    seg_resampled = sitk.Resample(
        seg, ref, sitk.Transform(),
        sitk.sitkNearestNeighbor, 0, seg.GetPixelID(),
    )
    mask_arr = sitk.GetArrayFromImage(seg_resampled)
```

Why this works on uniform-spacing data: SimpleITK handles SEG geometry correctly (PerFrameFunctionalGroups, orientation, segment palette) automatically. You get the right frames mapped to the right slices for free.

## The manual path (non-uniform spacing or multi-acq or duplicate-z)

When the simple path is unsafe, decode frames manually with pydicom and route them by SOP-UID (mirroring `sop_uid_routing.md`):

```python
import pydicom
import numpy as np

ds = pydicom.dcmread(seg_dicom_path)
frames = ds.pixel_array            # (N_frames, H, W) bool/uint8
pf_groups = ds.PerFrameFunctionalGroupsSequence

# Extract per-frame source SOP UID anchor (the slice the frame was drawn on)
def frame_source_sop_uid(per_frame_fg):
    try:
        return per_frame_fg.DerivationImageSequence[0] \
                          .SourceImageSequence[0].ReferencedSOPInstanceUID
    except (AttributeError, IndexError):
        return None

# Route every frame: prefer SOP UID, fall back to nearest-z only when UID absent.
for i, pfg in enumerate(pf_groups):
    sop_uid = frame_source_sop_uid(pfg)
    if sop_uid and sop_uid in sop_to_acq:
        # Find the CT slice index by SOP UID
        target_slice = ct_sop_to_slice_idx[sop_uid]
    else:
        # Fallback: read the frame's own ImagePositionPatient and snap to nearest z
        z = float(pfg.PlanePositionSequence[0].ImagePositionPatient[2])
        target_slice = int(np.argmin(np.abs(np.array(ct_z_positions) - z)))
    mask[target_slice] |= frames[i]
```

Track the SOP-UID-vs-fallback split as telemetry (see `sop_uid_routing.md`). On clean data, fallback should be 0%; on EAY131 SEG it was 0% in V6.

## Lesson learned — PROSTATEx-Seg-HiRes (2026-04-10)

Defaulting to manual pydicom SEG decoding (learned from EAY131 CT non-uniform z-spacing bugs) caused **38/66 failures** when applied to MRI data with uniform spacing. The manual approach introduced a direction-matrix transposition bug. `sitk.ReadImage()` + nearest-neighbour resample solved it cleanly. The workaround was harder than the problem.

**Takeaway:** the audit/uniformity check is the gate. If z is uniform, take the simple path; the manual path's complexity is liability, not robustness.

## Common pitfalls

- Treating "I once needed manual decoding for dataset X" as a universal rule. Different datasets have different traps; check each one.
- Using `sitk.Resample` with `sitkLinear` for masks. Always nearest-neighbour for masks (`sitk.sitkNearestNeighbor`); linear produces fractional values.
- Forgetting that `pixel_array` for SEG is shape `(N_frames, H, W)`, not `(Z, H, W)`. The frame-to-slice mapping is what `PerFrameFunctionalGroupsSequence` is for.
- Assuming all frames belong to the same segment (label). Multi-segment SEG has per-frame `SegmentIdentificationSequence.ReferencedSegmentNumber` you must respect.
