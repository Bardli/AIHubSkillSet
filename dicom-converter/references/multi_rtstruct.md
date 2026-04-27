# Multi-RTSTRUCT Handling (Iterate Every File, OR-Union ROIs)

Many clinical pipelines (RayStation, MIM, in-house exporters) emit **one RTSTRUCT `.dcm` per ROI** in the annotation directory. Reading only `dcm_files[0]` silently drops N-1 ROIs.

## Measured impact

EAY131-8365856 acq2 (April 2026): a single-file parse produced **13,929 voxels**. The OR-union of all 8 RTSTRUCT files in the directory produced **145,642 voxels** — a **10× undercount**, and the root cause of the P0 image_slices NCC collapse in Smoke Run 2.

## The pattern

Iterate every `*.dcm` in the annotation directory. Filter on `Modality == "RTSTRUCT"`. Concatenate the parsed contour lists from every file. The downstream rasterizer ORs them voxel-wise (any contour that paints a voxel turns it on).

```python
import pydicom
from pathlib import Path

def parse_rtstruct_dir(annotation_dir):
    """Iterate every *.dcm in annotation_dir, OR-union all RTSTRUCT ROIs.

    Returns a flat list of contour dicts (with sop_uid anchors), or None
    if no RTSTRUCT was found.
    """
    results = []
    for f in sorted(Path(annotation_dir).glob("*.dcm")):
        try:
            ds = pydicom.dcmread(str(f))
        except (pydicom.errors.InvalidDicomError, IsADirectoryError):
            continue
        if getattr(ds, "Modality", None) != "RTSTRUCT":
            continue
        results.extend(parse_one_rtstruct(ds))
    return results if results else None
```

The bundled `scripts/parse_rtstruct_union.py` is a complete CLI implementation that records each contour's SOP-UID anchor (see `sop_uid_routing.md`).

## Why "first file only" is so common

- Most public datasets bundle one RTSTRUCT per study, so single-file parsing happens to work and the bug never surfaces.
- Tutorials and example notebooks (including some popular ones) parse a single file; the pattern propagates.
- The failure mode is silent: the script runs to completion, produces a non-empty mask, and nothing flags the missing voxels until you compare against ground truth.

## How to detect this trap before it bites

Audit check #6 (see `audit_checklist.md`): if the annotation directory has more than one `*.dcm` with `Modality == "RTSTRUCT"`, stop and switch to the union parser. The bundled `scripts/audit_dicom_dataset.py` flags this automatically.

## What the union does NOT solve

- **Cross-acquisition leakage.** If the source data has multi-acquisition under one SeriesUID, the union still needs SOP-UID routing per contour to land on the right acquisition. Apply both patterns together. See `sop_uid_routing.md`.
- **Bad ROIs (seed points, unintended structures).** Filter by `ROI Name` *before* unioning, not after, or you accumulate spurious contours. Common skips: 2-point `CLOSED_PLANAR` "SEED POINT" ROIs (rasterizes to empty / single voxel; suppress at parse time).
- **Multiple physicians' annotations.** If the directory contains both "physician A" and "physician B" RTSTRUCTs, the union merges them. That may or may not be what you want — confirm with the user.

## Common pitfalls

- Globbing `*.dcm` case-insensitively is needed on some filesystems (`*.dcm` and `*.DCM` differ on case-sensitive filesystems). Use `Path.glob("*.[dD][cC][mM]")` or normalize at ingest.
- Reading every file with `dcmread()` (no `stop_before_pixels=True`) is slow but unavoidable here — RTSTRUCT parsing needs the full sequence, not just the header. For the audit step, header-only is enough; for the union parse, read fully.
- Treating directory iteration as ordered: `Path.glob()` order is filesystem-dependent. Always `sorted()` for determinism.
