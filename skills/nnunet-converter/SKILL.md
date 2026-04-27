---
name: nnunet-converter
description: >
  Convert medical imaging datasets into nnUNet v2 format. Supports all nnUNet-native
  formats: NIfTI (.nii.gz), MHA (.mha), NRRD (.nrrd), PNG (.png), BMP (.bmp), TIFF (.tif).
  Use this skill whenever the user mentions nnUNet, nnU-Net, dataset conversion for
  segmentation training, preparing data for nnUNet, organizing imagesTr/labelsTr folders,
  generating dataset.json, or structuring medical images for nnUNet preprocessing.
  Trigger even if the user just says "convert my dataset to nnUNet" or "prepare my
  segmentation data for nnUNet training". Also handles classification labels (cls_data.csv)
  and classification_labels in dataset.json.
---

# nnUNet v2 Dataset Converter Skill

Convert datasets into nnUNet v2 format with **minimal unnecessary conversion**.
nnUNet v2 natively supports many file formats — avoid format conversion whenever possible.

This SKILL.md is intentionally compact. Detailed guidance lives in `references/*.md` and is
loaded **on demand** based on the input dataset's characteristics. The pointer table at the
end of this file tells you exactly which reference to read for a given situation. Mandatory
references are flagged with **MUST read** — those are non-negotiable.

---

## Core Principle: Minimize Conversion

nnUNet v2 supports multiple file formats natively via its `ReaderWriter` abstraction.
**Do NOT convert files to a different format unless strictly necessary.**

- `.nii.gz` → keep as `.nii.gz`
- `.mha` → keep as `.mha` (do NOT convert to `.nii.gz`)
- `.nrrd` → keep as `.nrrd`
- 2D `.png` / `.bmp` → keep as `.png` / `.bmp` (do NOT wrap in NIfTI)
- `.tif` / `.tiff` → keep as `.tif`
- `.jpg` / `.jpeg` → **must** convert to `.png` (JPEG is lossy; nnUNet requires lossless)

The only valid reasons to convert format are:
1. Input uses lossy compression (`.jpg`) — convert to `.png`.
2. Mixing formats within a dataset (nnUNet requires one `file_ending` per dataset).
3. Input format is not supported by any nnUNet ReaderWriter.

## Supported File Formats (official nnUNet docs)

| ReaderWriter         | Extensions                    | Notes |
|---|---|---|
| **NaturalImage2DIO**     | `.png`, `.bmp`, `.tif`        | 2D natural images. RGB stored in a single file (no channel split). |
| **NibabelIO**            | `.nii.gz`, `.nrrd`, `.mha`    | Standard 3D medical imaging. |
| **NibabelIOWithReorient**| `.nii.gz`, `.nrrd`, `.mha`    | Same as NibabelIO, reorients to RAS. |
| **SimpleITKIO**          | `.nii.gz`, `.nrrd`, `.mha`    | Alternative 3D reader. |
| **Tiff3DIO**             | `.tif`, `.tiff`               | 3D TIFF stacks. Requires companion `.json` with spacing. |

**IMPORTANT:** nnUNet requires lossless (or no) compression. No `.jpg`.

## nnUNet v2 Folder Layout

```
nnUNet_raw/
└── Dataset{ID}_{Name}/        # e.g. Dataset042_LiverSeg
    ├── dataset.json
    ├── imagesTr/
    │   ├── case_0001_0000.nii.gz   # channel 0 of case 0001
    │   ├── case_0001_0001.nii.gz   # channel 1 (multi-modal only)
    │   └── ...
    ├── labelsTr/
    │   ├── case_0001.nii.gz        # segmentation mask (NO channel suffix)
    │   └── ...
    └── imagesTs/                   # optional test images (no labels needed)
        └── ...
```

**File naming rule:** `{CASE_ID}_{XXXX}.{FILE_ENDING}` for images, `{CASE_ID}.{FILE_ENDING}` for labels.

- `CASE_ID`: any string, e.g. `liver_001`, `BRATS_042`.
- `XXXX`: 4-digit zero-padded channel identifier (`_0000`, `_0001`, ...).
- Single modality: only `_0000` exists.
- Labels: **no** channel suffix.
- **RGB exception:** for `.png` RGB natural images, all 3 colour channels are stored in a single file with suffix `_0000`. Do NOT split RGB into separate files. Details in `references/2d_images.md`.

---

## Workflow

The five steps below are the canonical conversion flow. Each step lists the references you
**must** load before doing the work for the relevant scenario.

### Step 1 — Understand the Input Dataset

Before writing any code, determine:

1. **Source layout** — flat folders, per-subject folders, mixed, or class-folder 2D.
   → If layout is non-trivial or unfamiliar, you **MUST** read `references/input_layouts.md` before pairing images with labels.
2. **Modalities / channels** — single, multi-modal, or RGB natural image.
3. **File format** — already supported (keep), `.jpg` (convert to `.png`), or unsupported (convert to nearest supported).
4. **Label values** — must be consecutive integers starting at 0, with 0 = background.
5. **Train/test split** — pre-defined or all into `imagesTr`?
6. **Dataset ID and CamelCase name** — 3-digit ID. IDs 001–010 are reserved for the Medical Segmentation Decathlon.
7. **Channel names** — these control nnUNet normalization. Common values:
   - `"CT"` → CT-specific global normalization (clip 0.5/99.5 percentile + z-score on foreground).
   - `"noNorm"` → no normalization.
   - `"rescale_to_0_1"` → rescale intensities to `[0, 1]`.
   - `"rgb_to_0_1"` → uint8 / 255 (use for RGB natural images).
   - `"zscore"` or anything else → per-image z-score (default for MRI).
   - The exact string matters — it selects the normalization scheme.
8. **Classification labels** — case-level labels in addition to segmentation?
   → If yes, you **MUST** read `references/classification_labels.md` before writing any classification CSV or `classification_labels` block.
9. **Spatial alignment** — for multi-modal, do all modalities share size/spacing/origin/direction?
   → If any differ, you **MUST** read `references/multi_modal.md` before the conversion script touches imaging data.

### Step 2 — Write the Conversion Script

Use `scripts/convert_template.py` as a starting point for **complex / non-NIfTI inputs**.

**Shortcut for the simple-NIfTI case:** if and only if all of these hold —
- inputs are 3D `.nii.gz`,
- per-case layout is exactly `raw-dir/images/<case>_<chan>.nii.gz` + `raw-dir/labels/<case>.nii.gz`,
- labels are already contiguous integers starting at 0,
- no classification labels, no ignore label, no region-based labels,
- no spatial-resampling needed across modalities

— you MAY use `scripts/make_nnunet_dataset_simple.py` directly instead of writing your own script. It copies files, writes `dataset.json`, and writes a seeded `splits_final.json` in one shot. Do **not** use it for any other layout.

Choose dependencies by input format:
- `.nii.gz` / `.mha` / `.nrrd` → `SimpleITK` or `nibabel`.
- `.png` / `.jpg` / `.bmp` → `Pillow`.
- `.tif` / `.tiff` (2D) → `Pillow`. `.tif` (3D stacks) → `tifffile`.

Mandatory pre-reads, depending on the data you have:

- **2D images (PNG/BMP/TIFF, including RGB natural images):** you **MUST** read `references/2d_images.md` before writing any conversion code.
- **3D TIFF stacks (microscopy, OCT, multi-frame TIFF):** you **MUST** read `references/3d_tiff.md` before writing any conversion code.
- **Multi-modal data with different resolutions:** you **MUST** read `references/multi_modal.md` before writing any conversion code.
- **Labels with non-consecutive values, ignore regions, or overlapping/region-based targets (e.g. BraTS):** you **MUST** read `references/label_handling.md` before writing any label-remapping code.
- **Classification labels of any kind:** you **MUST** read `references/classification_labels.md` before writing `cls_data.csv` or `classification_labels`.

Universal rules to enforce in the script:

- If input is already in a supported format, copy/rename — do not re-encode.
- Output extension must match `file_ending` in `dataset.json`.
- All images must use the same `file_ending` across the dataset.
- Labels never carry a channel suffix.
- Case identifiers must be consistent between `imagesTr` and `labelsTr`.
- Validate that label values are consecutive integers starting at 0.
- For `.jpg` / `.jpeg` inputs, convert to `.png` (lossless).

### Step 3 — Generate dataset.json

You **MUST** read `references/dataset_json_spec.md` before writing or modifying `dataset.json`. Do not rely on memory of the schema — required fields and optional fields both have subtle rules (e.g. `sort_keys=False` for region-based labels).

Minimal required fields:
```json
{
  "channel_names": {"0": "CT"},
  "labels": {"background": 0, "liver": 1},
  "numTraining": 51,
  "file_ending": ".nii.gz"
}
```

Optional but recommended: `name`, `description`, `reference`, `licence`, `overwrite_image_reader_writer`.

> `overwrite_image_reader_writer` is **optional** — nnUNet auto-detects the correct ReaderWriter from the file extension. Set it only if auto-detection fails or you need a specific reader (e.g., `NibabelIOWithReorient` to force RAS reorientation, or `Tiff3DIO` for 3D TIFF stacks).

### Step 4 — Validate

```bash
ls imagesTr/ | wc -l    # should equal numTraining * num_channels
ls labelsTr/ | wc -l    # should equal numTraining
ls imagesTr/ | head -5  # spot-check naming
ls labelsTr/ | head -5

# If nnUNet is installed:
nnUNetv2_plan_and_preprocess -d {ID} --verify_dataset_integrity
```

### Step 5 — Update Conversion Notes (MANDATORY)

After every successful conversion you **MUST** read `references/conversion_notes_template.md` and append a fully-populated entry to `conversion_notes.md` in the `nnUNet_raw/` directory. This step is **non-negotiable** — it is the only durable record of source paths, dropped files, label mapping, and licence.

If `conversion_notes.md` does not exist, create it with a `# nnUNet Dataset Conversion Notes` header first.

Skipping this step is treated as an incomplete conversion.

### Step 6 — Generate splits_final.json + Optional Provenance

If the user wants reproducible cross-validation (almost always — anything that will train a model needs frozen splits), you **MUST** read `references/splits_and_provenance.md` before generating `splits_final.json`. The reference covers:

- Where `splits_final.json` lives (`$nnUNet_preprocessed`, **not** `$nnUNet_raw`).
- Required JSON shape and case-ID rules.
- Seeded patient-level split generation (the simple CLI writes this for you; otherwise use the inline pattern in the reference).
- The optional machine-readable `_manifest.json` companion (run `scripts/write_manifest.py`). This is **optional** but recommended; the mandatory human-readable record is still `conversion_notes.md` (Step 5).

Record the seed and `num_folds` in your Step 5 conversion-notes entry under **Notes**.

---

## Other scenarios

| Situation | What you MUST read |
|---|---|
| Migrating from MSD or nnU-Net v1 | `references/migration_and_inference.md` |
| Setting up `nnUNet_raw` / `nnUNet_preprocessed` / `nnUNet_results` env vars | `references/migration_and_inference.md` |
| Preparing inference inputs to match a trained model | `references/migration_and_inference.md` |
| Writing a custom `splits_final.json` for cross-validation | `references/splits_and_provenance.md` (preferred) or `references/migration_and_inference.md` (older brief) |

---

## Pointer Reference Table

When the situation matches the **left** column, the rule on the **right** is mandatory.

| Situation | Action |
|---|---|
| 2D images (PNG / BMP / TIFF including RGB) | **MUST** read `references/2d_images.md` before writing conversion code. |
| 3D TIFF stacks (Tiff3DIO, multi-frame TIFF) | **MUST** read `references/3d_tiff.md` before writing conversion code. |
| Multi-modal MRI / different resolutions per modality | **MUST** read `references/multi_modal.md` before writing conversion code. |
| Case-level classification labels (`cls_data.csv`) | **MUST** read `references/classification_labels.md` before writing classification metadata. |
| Label remapping, ignore label, region-based training | **MUST** read `references/label_handling.md` before writing label code. |
| Non-trivial / unfamiliar source folder layout | **MUST** read `references/input_layouts.md` before pairing images with labels. |
| Writing or editing `dataset.json` | **MUST** read `references/dataset_json_spec.md` before writing JSON. |
| **Step 5 — Conversion notes (every conversion)** | **MUST** read `references/conversion_notes_template.md` and append the fully-populated entry. |
| Generating `splits_final.json` or the optional `_manifest.json` | **MUST** read `references/splits_and_provenance.md` before generating either file. |
| MSD / nnU-Net v1 migration, env vars, inference, custom splits | **MUST** read `references/migration_and_inference.md`. |

---

## Files in this skill

```
nnunet-converter/
├── SKILL.md                                  # This file (entry point)
├── references/
│   ├── dataset_json_spec.md                  # dataset.json field reference
│   ├── 2d_images.md                          # PNG / BMP / RGB natural images
│   ├── 3d_tiff.md                            # Tiff3DIO + companion .json spacing
│   ├── multi_modal.md                        # multi-channel layout + spatial resampling
│   ├── classification_labels.md              # cls_data.csv + classification_labels
│   ├── label_handling.md                     # validation, ignore label, region-based
│   ├── input_layouts.md                      # Layouts A / B / C / D
│   ├── conversion_notes_template.md          # mandatory Step 5 log template
│   ├── splits_and_provenance.md              # splits_final.json + optional _manifest.json
│   └── migration_and_inference.md            # env vars, MSD/v1, splits, inference
├── scripts/
│   ├── convert_template.py                   # reusable Python conversion template (complex inputs)
│   ├── make_nnunet_dataset_simple.py         # CLI for the simple 3D-NIfTI case (writes splits_final.json)
│   └── write_manifest.py                     # optional _manifest.json provenance writer
└── README.md
```

Both `make_nnunet_dataset_simple.py` and `write_manifest.py` were adapted from
[ryanwangk/medimg_skills](https://github.com/ryanwangk/medimg_skills) (MIT). Acquisition
of medical datasets (TCGA/GDC, Kaggle, HuggingFace, Google Drive, sbatch) is intentionally
out of scope here — it lives in a separate `dataset-acquisition` skill.
