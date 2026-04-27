# nnUNet v2 dataset.json Field Reference

## Required Fields

### `channel_names` (dict, required)
Maps channel index string → modality name string.
```json
"channel_names": {
  "0": "CT"
}
```
```json
"channel_names": {
  "0": "T1",
  "1": "T1Gd",
  "2": "T2",
  "3": "FLAIR"
}
```
**Critical**: The string value controls normalization scheme:
- `"CT"` → global foreground normalization (clip to 0.5/99.5 percentile, z-score on foreground intensities)
- `"noNorm"` → no normalization at all
- `"rescale_to_0_1"` → rescale intensities to [0, 1]
- `"rgb_to_0_1"` → assumes uint8 input, divides by 255 (use for RGB natural images)
- `"zscore"` or anything else → per-image z-score normalization (default for MRI)

### `labels` (dict, required)
Maps label name → integer value. **name:int** (NOT int:name like nnUNet v1).
```json
"labels": {
  "background": 0,
  "liver": 1,
  "tumor": 2
}
```
Rules:
- `background` must map to `0`
- If there is no background, do not use label 0 for something else
- Values must be consecutive integers: 0, 1, 2, 3, ...
- No gaps allowed
- Not all labels need to be present in every training case

### `numTraining` (int, required)
Number of training cases (i.e., number of entries in `imagesTr` / number of unique case IDs, NOT number of files).

### `file_ending` (string, required)
File extension used for ALL images and segmentations. Must be identical for images and labels.

Supported values (match the input data format — avoid unnecessary conversion):
- `.nii.gz` — NIfTI compressed (3D volumetric data: CT, MRI)
- `.nii` — NIfTI uncompressed
- `.mha` — MetaImage (natively supported, no need to convert to .nii.gz)
- `.nrrd` — Nearly Raw Raster Data (natively supported)
- `.png` — 2D natural images (endoscopy, dermoscopy, histology, surgical). RGB stored in single file.
- `.bmp` — 2D bitmap images
- `.tif` / `.tiff` — 2D images or 3D stacks (3D requires companion .json with spacing)

**IMPORTANT**: nnUNet requires **lossless** compression only. No `.jpg`/`.jpeg`!

**Principle**: Use the format your data is already in. Do not convert unless necessary.

---

## Optional Fields

### `name` (string)
Human-readable dataset name. Not used by nnUNet but useful for documentation.
```json
"name": "Dataset042_LiverSeg"
```

### `description` (string)
Free text description. Not used by nnUNet.

### `reference` (string)
Citation or URL for the dataset. Not used by nnUNet.

### `licence` (string)
Data license. Not used by nnUNet.

### `overwrite_image_reader_writer` (string)
Force a specific IO backend. **Optional** — nnUNet auto-detects the correct reader based on file extension.
Only set this if auto-detection fails or you need a specific behavior:
- `"SimpleITKIO"` — alternative reader for `.nii.gz`, `.nrrd`, `.mha`
- `"NibabelIO"` — NIfTI reader via nibabel
- `"NibabelIOWithReorient"` — like NibabelIO but reorients images to RAS
- `"NaturalImage2DIO"` — for `.png`, `.bmp`, `.tif` 2D images
- `"Tiff3DIO"` — for 3D TIFF stacks (requires companion `.json` with spacing)

### `classification_labels` (dict)
Case-level classification labels. Maps a task name → {class_int: class_name}.
Must be paired with a `cls_data.csv` file at the dataset root.
```json
"classification_labels": {
  "ISUP_grade": {
    "0": "Benign/Indolent (ISUP 0-1)",
    "1": "ISUP 1",
    "2": "ISUP 2",
    "3": "ISUP 3",
    "4": "ISUP 4",
    "5": "ISUP 5"
  }
}
```
The `cls_data.csv` format:
```csv
identifier,label
case_001,0
case_002,3
```
Where `identifier` matches the case ID in imagesTr/labelsTr (no channel suffix, no extension),
and `label` is the integer class. For multi-label tasks, use list format: `"[1, 0]"`.

### `regions_class_order` (list, only for region-based training)
Only needed if using hierarchical/overlapping labels. Leave out for standard segmentation.
Tells nnUNet how to convert region predictions back to integer label maps.
Order matters: encompassing regions first, substructures last (later entries overwrite earlier ones).
Length must equal number of regions (excluding background).
```json
"labels": {
    "background": 0,
    "whole_tumor": [1, 2, 3],
    "tumor_core": [2, 3],
    "enhancing_tumor": 3
},
"regions_class_order": [1, 2, 3]
```
**IMPORTANT**: Use `sort_keys=False` in `json.dump()` to preserve label declaration order!

### Ignore label
For sparse/incomplete annotations. Must be the **highest** integer value and named `"ignore"`:
```json
"labels": {
    "background": 0,
    "organ": 1,
    "tumor": 2,
    "ignore": 3
}
```
Ignored regions are excluded from loss computation. nnUNet still predicts dense segmentations at inference.

---

## Full Example — Single-Modality CT (.nii.gz)
```json
{
  "name": "Dataset042_LiverSeg",
  "description": "Liver segmentation from abdominal CT",
  "reference": "https://example.com/dataset",
  "licence": "CC-BY 4.0",
  "channel_names": {
    "0": "CT"
  },
  "labels": {
    "background": 0,
    "liver": 1,
    "tumor": 2
  },
  "numTraining": 131,
  "file_ending": ".nii.gz"
}
```

## Full Example — Multi-Modal MRI (.nii.gz)
```json
{
  "name": "Dataset043_BrainTumour",
  "description": "Glioma segmentation from multi-modal MRI",
  "channel_names": {
    "0": "T1",
    "1": "T1Gd",
    "2": "T2",
    "3": "FLAIR"
  },
  "labels": {
    "background": 0,
    "enhancing_tumor": 1,
    "necrotic_core": 2,
    "edema": 3
  },
  "numTraining": 484,
  "file_ending": ".nii.gz"
}
```

## Full Example — 2D RGB PNG (Endoscopy/Surgical)
```json
{
  "name": "Dataset060_EndoSeg",
  "description": "2D endoscopy instrument segmentation",
  "channel_names": {
    "0": "R",
    "1": "G",
    "2": "B"
  },
  "labels": {
    "background": 0,
    "instrument": 1,
    "tissue": 2
  },
  "numTraining": 1200,
  "file_ending": ".png"
}
```
Note: Despite 3 channel names, each image is stored as a single RGB `.png` with `_0000` suffix.

## Full Example — MHA (kept as-is, no conversion)
```json
{
  "name": "Dataset050_Prostate",
  "channel_names": {
    "0": "T2"
  },
  "labels": {
    "background": 0,
    "prostate": 1
  },
  "numTraining": 32,
  "file_ending": ".mha"
}
```

## Full Example — 3D TIFF with spacing
```json
{
  "name": "Dataset123_CellSeg",
  "channel_names": {
    "0": "Fluorescence"
  },
  "labels": {
    "background": 0,
    "cell": 1
  },
  "numTraining": 50,
  "file_ending": ".tif",
  "overwrite_image_reader_writer": "Tiff3DIO"
}
```
Each `.tif` file needs a companion `.json` with spacing: `{"spacing": [0.5, 0.5, 2.0]}`
