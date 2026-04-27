# Migration, Environment, Inference, and Custom Splits

## Environment variables

nnUNet requires three environment variables to be set before running any commands:

```bash
export nnUNet_raw="/path/to/nnUNet_raw"
export nnUNet_preprocessed="/path/to/nnUNet_preprocessed"   # should be on fast storage (SSD)
export nnUNet_results="/path/to/nnUNet_results"
```

The conversion script outputs data to `$nnUNet_raw`. After conversion, the user must export these variables before running `nnUNetv2_plan_and_preprocess`.

## Inference data format

The data format for inference **must match training exactly**:
- Same `file_ending` as specified in `dataset.json`.
- Same channel order and naming convention (`{CASE_ID}_{XXXX}.{FILE_ENDING}`).
- All input channels must be present for every case.
- You cannot train on `.png` and run inference on `.jpg` — pick the lossless training format and stick with it.

## Migrating existing datasets

### From Medical Segmentation Decathlon (MSD)

```bash
nnUNetv2_convert_MSD_dataset -i /path/to/TaskXXX_Name -o DatasetXXX_Name
```

### From nnU-Net v1

```bash
nnUNetv2_convert_old_nnUNet_dataset /path/to/old/TaskXXX_Name DatasetXXX_Name
```

### Key differences from v1

- `"modality"` is now `channel_names`.
- Labels are `name: int` (NOT `int: name`).
- Datasets are `DatasetXXX_Name` (NOT `TaskXXX`).
- `file_ending` field is new (and supports multiple formats).

## Custom data splits

By default nnUNet uses 5-fold cross-validation with random splits. To use custom splits:

1. Create a `splits_final.json` in `nnUNet_preprocessed/DatasetXXX_NAME/`.
2. Format: list of 5 dicts, each with `"train"` and `"val"` keys containing lists of case identifiers.

```json
[
    {"train": ["case_001", "case_002"], "val": ["case_010", "case_011"]},
    {"train": ["case_003", "case_004"], "val": ["case_001", "case_002"]}
]
```

Identifiers must match the case IDs used in `imagesTr` / `labelsTr` filenames (no channel suffix, no extension).

## Validation after conversion

```bash
# Count files match
ls imagesTr/ | wc -l   # should equal numTraining * num_channels
ls labelsTr/ | wc -l   # should equal numTraining

# Spot-check naming
ls imagesTr/ | head -5
ls labelsTr/ | head -5

# If nnUNet is installed, run the integrity check
nnUNetv2_plan_and_preprocess -d {ID} --verify_dataset_integrity
```
