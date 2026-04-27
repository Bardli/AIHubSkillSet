# SOP-UID Routing (Step 0 — the highest-leverage rule)

Labeling software (RayStation, MIM, …) records *exactly which 2D image the physician was viewing* when each contour was drawn. That reference is the ground truth for slice assignment — **read it first, route by it, do not match contours to slices by z-coordinate geometry.**

This single architectural choice eliminates a whole class of "downstream" bugs that look unrelated.

## Where the SOP-UID anchor lives

- **RTSTRUCT (per contour):**
  ```
  ROIContourSequence[k].ContourSequence[i].ContourImageSequence[0].ReferencedSOPInstanceUID
  ```
- **DICOM SEG (per frame):**
  ```
  PerFrameFunctionalGroupsSequence[i].DerivationImageSequence[0].SourceImageSequence[0].ReferencedSOPInstanceUID
  ```

Both name the exact CT/MR slice the annotation belongs to. Use it.

## The pattern

```python
import pydicom

# 1. Build SOP-UID → AcquisitionNumber map from CT headers (per series, once).
sop_to_acq = {}
for f in ct_files:
    ds = pydicom.dcmread(f, stop_before_pixels=True)
    sop_to_acq[ds.SOPInstanceUID] = int(getattr(ds, "AcquisitionNumber", 1))

# 2. parse_rtstruct: capture per-contour SOP UID anchor.
for contour in roi.ContourSequence:
    cis = getattr(contour, "ContourImageSequence", None)
    sop_uid = cis[0].ReferencedSOPInstanceUID if cis else None
    contours.append({"points": ..., "sop_uid": sop_uid, ...})

# 3. Route by SOP UID first; nearest-z is fallback ONLY when UID absent/unknown.
def route_for_acq(mean_z, acq_num, z_positions, all_acq_z, sop_uid, sop_to_acq):
    if sop_uid and sop_to_acq and sop_uid in sop_to_acq:
        return "keep" if sop_to_acq[sop_uid] == acq_num else "skip"
    return belongs_to_acq_nearest_z(mean_z, acq_num, z_positions, all_acq_z)

# 4. SEG: same pattern, source UID lives in DerivationImageSequence.
def frame_source_sop_uid(per_frame_fg):
    try:
        return per_frame_fg.DerivationImageSequence[0] \
                          .SourceImageSequence[0].ReferencedSOPInstanceUID
    except (AttributeError, IndexError):
        return None
```

The bundled `scripts/build_sop_to_acq.py` does step (1) for you and emits a JSON map you can pass to any rasterizer.

## Symptoms that disappear once you route by SOP UID

| Symptom that LOOKS like its own bug | Actually a missed metadata read |
|---|---|
| "Contours outside z-range" rejected/clamped | Contour was anchored to a specific CT slice; no z-range check needed. |
| Same contour leaks into two acquisitions on shared-z slices | SOP UID picks the right acquisition; geometry can't disambiguate. |
| Annotators drew on a "merged" multi-acq view; SEG frames alternate | Each frame names its source CT slice — handle them one by one. |
| Off-by-one slice from non-uniform z-spacing | Slice is named by UID, not derived from a z-grid. |
| Mask "shifted by a couple slices" after dedup/sort changes | UID survives sort changes; z-coordinate doesn't. |

## Quantified impact (EAY131 V3 → V6, 2026-04-26)

V3's nearest-z heuristic over-applied **851 / 2,462 RTSTRUCT contours (35%)** across 7 case_ids. V6 SOP-UID routing:

- Purged 4.6M spurious GT voxels.
- Dropped 56 fully-spurious case_ids.
- Required nearest-z fallback for only **660 / 84,539 contours (~0.8%)** — the truly absent-UID cases.
- For DICOM SEG frames: **0 fallback** (every frame had a `SourceImageSequence`).

If you measure your own fallback rate well above 1%, the data is unusually dirty — flag it and consider whether the source pipeline emitting the annotations is correct.

## Hard rules

1. **Read RTSTRUCT/SEG metadata before rasterizing.** The SOP-UID is in the header. Step 0 is header-only.
2. **Iterate ALL `*.dcm` in the annotation directory.** Many pipelines emit one RTSTRUCT file per ROI; reading only `dcm_files[0]` silently drops N-1 ROIs. See `multi_rtstruct.md`.
3. **Build `sop_to_acq` from the full per-acquisition file list, not from a z-deduped subset.** A z-dedup that prunes `sop_to_acq` re-introduces nearest-z fallback for any duplicate-z slice and silently leaks contours back into the wrong acquisition (EAY131 V6 dedup bug, patched 2026-04-26).
4. **Nearest-z is fallback only.** Never the primary routing. Track the fallback rate as a data-cleanliness signal.
5. **For SEG, mirror the pattern in `convert_seg_to_mask`.** Use `DerivationImageSequence[0].SourceImageSequence[0].ReferencedSOPInstanceUID` per frame. Fixing RTSTRUCT routing while leaving SEG on a `_belongs_to_acq` heuristic perpetuates the bug for SEG-annotated cohorts.
