---
name: dicom-converter
description: Use when converting DICOM series to NIfTI, handling RTSTRUCT/SEG annotations, auditing a DICOM dataset's health (clean vs dirty), routing per-contour or per-frame masks to the correct slice/acquisition, or debugging DICOM→NIfTI label misalignment. Triggers on keywords like DICOM, NIfTI, nii.gz, RTSTRUCT, SEG, SimpleITK, ImageSeriesReader, pydicom, ImagePositionPatient, AcquisitionNumber, SOPInstanceUID, ContourImageSequence, DerivationImageSequence, multi-acquisition, z-spacing, sop_to_acq.
---

# DICOM Converter

How to take a directory of DICOM files and produce correct NIfTI images and label masks. The skill is structured around two non-negotiable rules:

1. **Audit before you convert.** A 30-second header-only audit decides whether the simple path is safe.
2. **Route annotations by SOP-UID, not by z-coordinate geometry.** This single architectural choice eliminates a whole class of bugs that look unrelated.

This SKILL.md is intentionally compact. Detailed guidance lives in `references/*.md` and is loaded **on demand** based on what the input data and task require. Mandatory pre-reads are flagged with **MUST read** — those are non-negotiable.

---

## Pipeline at a glance

```
DICOM (raw)
  │  Stage 1: DICOM → NIfTI (HARD — metadata traps)
  ▼
NIfTI (image + label pairs)
  │  Stage 2: NIfTI → NPZ (EASY — but windowing matters)
  ▼
NPZ (uint8 image + instance labels + RECIST prompts)
  │  Stage 3: Inference (model-specific)
  ▼
Predictions → Evaluation (DSC, visualization)
```

The hard part is Stage 1. Stages 2 and 3 are mechanical — see `references/downstream_stages.md` when you need them.

---

## Workflow

### Step 1 — Audit the dataset (always)

You **MUST** read `references/audit_checklist.md` and run `scripts/audit_dicom_dataset.py` before deciding which converter to run. The auditor checks 10 cleanliness conditions header-only and exits `0` clean / `1` dirty. Use it to gate every new dataset.

```bash
python scripts/audit_dicom_dataset.py --root /path/to/dataset --csv audit.csv
```

Decision rule:

```
all green  →  use the simple converter (sitk.ImageSeriesReader, single pass)
any red    →  use the metadata-first pipeline (per-acq split, sop_to_acq, SOP-UID routing)
hard error →  fail loudly; do not silently produce a corrupted NIfTI
```

### Step 2 — If dirty, build the SOP-UID → AcquisitionNumber map

You **MUST** read `references/sop_uid_routing.md` before writing any rasterizer that touches RTSTRUCT contours or SEG frames. Then run:

```bash
python scripts/build_sop_to_acq.py --series /path/to/ct_dir \
    --filter-localizer --out sop_to_acq.json
```

Build the map from the **full** per-acquisition file list. Never prune it during z-dedup — that re-introduces the silent leakage bug patched 2026-04-26. See the warnings in `references/image_stack_traps.md`.

### Step 3 — Convert images

Choose the path based on the audit verdict:

- **Clean → simple path:** `sitk.ImageSeriesReader` over the directory. Done.
- **Dirty (multi-acq, duplicate z, non-uniform z, mixed orientation):** you **MUST** read `references/image_stack_traps.md` before stacking. Split by `AcquisitionNumber`, dedup the image stack only, compute spacing from IPP differences, filter localizers, rotate non-axial.

### Step 4 — Convert annotations

Pick the right approach based on the annotation type:

- **DICOM SEG:** you **MUST** read `references/seg_decoding.md` to choose between the simple `sitk.ReadImage(seg_path)` path and the manual pydicom path. The decision tree is z-spacing-uniformity-based; the simple path is correct on most MRI and was the cure for the PROSTATEx-Seg-HiRes regression.
- **RTSTRUCT (single file):** apply SOP-UID routing per contour (`references/sop_uid_routing.md`) and rasterize onto the anchored slice using actual z-positions.
- **RTSTRUCT (annotation directory with multiple `.dcm` files):** you **MUST** read `references/multi_rtstruct.md` before parsing. Use `scripts/parse_rtstruct_union.py` to OR-union all RTSTRUCT files; reading only `dcm_files[0]` silently drops N-1 ROIs.

### Step 5 — Sanity-check before declaring success

If anything looks off (mask "shifted by a couple slices", wrong tissue HU, image-mask shape mismatch), you **MUST** read `references/debugging_misalignment.md`. The five checks there (HU at label, z-spacing recheck, multi-acq, multi-RTSTRUCT, `SliceThickness` vs reality) cover the vast majority of real failures.

### Step 6 — Downstream packing and inference

When packing to NPZ for MedSAM2-style inference or running competition Docker images, you **MUST** read `references/downstream_stages.md` — body-part-specific CT windowing and the universal Docker GPU fix are both in there. Wrong windowing destroys contrast; the GPU fix is the difference between minutes and hours per case.

### Step 7 — Visual QC

For per-case overlay PNGs, AI-assisted visual review with Claude Code, side-by-side comparisons, or grid videos, you **MUST** read `references/visualization_qc.md`. Includes the `best_slice = argmax(GT ∪ Pred)` rule (using `argmax(Pred)` alone produces empty-GT panels and misleads the reviewer).

---

## Pointer reference table

| Situation | Action |
|---|---|
| Any new dataset (always run first) | **MUST** read `references/audit_checklist.md` and run `scripts/audit_dicom_dataset.py`. |
| Writing any rasterizer (RTSTRUCT or SEG) | **MUST** read `references/sop_uid_routing.md`. Build `sop_to_acq.json` via `scripts/build_sop_to_acq.py`. |
| Annotation directory has more than one RTSTRUCT `.dcm` | **MUST** read `references/multi_rtstruct.md`. Use `scripts/parse_rtstruct_union.py`. |
| Multi-acquisition, duplicate z, non-uniform z, non-axial orientation | **MUST** read `references/image_stack_traps.md`. |
| Decoding a DICOM SEG file | **MUST** read `references/seg_decoding.md`. |
| Labels look shifted, HU wrong at label voxels, shape mismatch | **MUST** read `references/debugging_misalignment.md`. |
| Packing NIfTI → NPZ for inference, Docker GPU fix | **MUST** read `references/downstream_stages.md`. |
| Visual QC, per-case videos, AI-assisted review | **MUST** read `references/visualization_qc.md`. |
| EAY131 benchmark — evaluator, traps, key paths, naming, discipline | **MUST** read `references/eay131_benchmark.md`. |

---

## Files in this skill

```
dicom-converter/
├── SKILL.md                                  # This file (entry point)
├── references/
│   ├── audit_checklist.md                    # 10 cleanliness checks + decision rule
│   ├── sop_uid_routing.md                    # Step 0: route by SOP-UID, not geometry
│   ├── multi_rtstruct.md                     # Iterate every *.dcm; OR-union ROIs
│   ├── image_stack_traps.md                  # multi-acq, duplicate z, non-uniform z, orientation
│   ├── seg_decoding.md                       # sitk.ReadImage vs manual pydicom decision tree
│   ├── debugging_misalignment.md             # HU sanity, z-spacing recheck, common mistakes
│   ├── downstream_stages.md                  # NIfTI→NPZ windowing + Docker GPU fix
│   ├── visualization_qc.md                   # overlay QC, AI review, videos
│   └── eay131_benchmark.md                   # EAY131-specific evaluator + discipline
└── scripts/
    ├── audit_dicom_dataset.py                # 10-check header-only auditor (exits 0/1)
    ├── build_sop_to_acq.py                   # SOP-UID → AcquisitionNumber map writer
    └── parse_rtstruct_union.py               # Multi-RTSTRUCT OR-union with SOP-UID anchors
```
