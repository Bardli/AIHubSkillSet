# Classification Labels (cls_data.csv + dataset.json)

Many datasets have **case-level classification labels** in addition to segmentation masks. These are stored in two places, and BOTH must be written.

## cls_data.csv

A CSV file at the dataset root (sibling of `dataset.json`):

```csv
identifier,label
case_001,0
case_002,1
case_003,2
```

- `identifier`: matches the case ID used in `imagesTr` / `labelsTr` filenames (WITHOUT channel suffix or file extension).
- `label`: integer class label. Can also be a list for multi-label tasks: `"[1, 0]"` (use double quotes around the list literal).

## classification_labels in dataset.json

Add a `classification_labels` field to `dataset.json` mapping label names → meanings:

```json
{
  "classification_labels": {
    "ISUP_grade": {
      "0": "Benign/Indolent (ISUP 0-1)",
      "1": "ISUP 1",
      "2": "ISUP 2",
      "3": "ISUP 3"
    }
  }
}
```

For multi-label classification (e.g., primary tumor origin with multiple classes):
```json
{
  "classification_labels": {
    "primary_tumor_origin": {
      "0": "NSCLC",
      "1": "Breast carcinoma",
      "2": "SCLC"
    }
  }
}
```

## Where classification labels come from

- Clinical metadata CSV/spreadsheet (e.g., ISUP grade, IDH mutation status, tumor type)
- Derived from segmentation masks (e.g., presence/absence of tumor → binary classification)
- Folder structure or filename patterns

## Classification vs segmentation — choose meaningful targets

- Segmentation = voxel-level (WHERE is the lesion).
- Classification = case-level (WHAT type/grade is it).

If classification can be trivially derived from the segmentation mask (e.g., "has any tumor voxel"), prefer a richer classification target instead — tumor grade, molecular subtype, primary origin, etc.

## Existing examples in `/mnt/pool/datasets/CY/nnUNet_raw/`

- `Dataset219_BrainMets`: `primary_tumor_origin` (NSCLC / Breast / SCLC) — multi-class
- `Dataset227_MU_Glioma_Post`: `primary_diagnosis` (GBM / Astrocytoma / Others) — multi-class
- `Dataset306_JSC_UCSD_PTGB`: `idh_mutation_status` (IDH Wild-Type / IDH Mutant) — binary, with `-1` for unknown
- `Dataset211_BMLMPS_FLAIR`: multi-label format `"[1, 0]"`
- `Dataset320_PICAI`: `ISUP_grade` (0–5) — ordinal grading scale

## Common pitfalls

- Writing `cls_data.csv` but forgetting `classification_labels` in `dataset.json` (or vice versa) — both are required.
- Using a different identifier scheme in `cls_data.csv` than in filenames — they must match exactly.
- Including the file extension or channel suffix in the identifier — strip them.
