# Splits and Provenance

This reference covers two related topics: how to generate **reproducible
patient-level splits** (`splits_final.json`) and how to drop an **optional
machine-readable provenance manifest** (`_manifest.json`) next to your
dataset.

---

## Patient-level seeded splits (`splits_final.json`)

By default nnUNet randomly generates 5-fold splits the first time you run
`nnUNetv2_plan_and_preprocess`. That is fine for casual exploration but
fails three real requirements:

1. **Patient-level** splits — splits keyed on the case ID, not on individual
   slices/files. If you have multiple files per patient (multi-modal,
   multi-acquisition), random file-level splitting can put the same patient
   in both train and val; nnUNet's default keys on case ID so this is OK,
   but you still need to control which patient goes in which fold.
2. **Reproducible** — same seed → same splits, every time.
3. **Frozen before training** — once a model is trained, the splits must
   not silently change.

### Folder location

```
$nnUNet_preprocessed/Dataset<ID>_<Name>/splits_final.json
```

> **Note:** `splits_final.json` lives in `nnUNet_preprocessed`, not
> `nnUNet_raw`. nnUNet copies / regenerates it on first preprocess. Drop
> the file in the right location *before* `nnUNetv2_plan_and_preprocess`
> if you want to override.

### Format

A list of `num_folds` dicts, each with `"train"` and `"val"` keys whose
values are lists of bare case IDs (no channel suffix, no extension):

```json
[
  {"train": ["case001", "case003"], "val": ["case002", "case005"]},
  {"train": ["case001", "case002"], "val": ["case003", "case004"]}
]
```

Case IDs must match exactly the IDs used in `imagesTr/` / `labelsTr/`.

### Generating splits

If your input layout matches the simple
`raw-dir/images/<case>_<chan>.nii.gz` + `raw-dir/labels/<case>.nii.gz`
case (and your labels are already contiguous), use the bundled CLI:

```bash
python scripts/make_nnunet_dataset_simple.py \
    --raw-dir ./raw \
    --dataset-id 234 \
    --dataset-name PETCT \
    --channels CT PET \
    --labels "background,lesion" \
    --output-root $nnUNet_raw \
    --split-seed 42 \
    --num-folds 5
```

The script writes both `dataset.json` and `splits_final.json` (alongside
`imagesTr/` and `labelsTr/`). Move/copy `splits_final.json` into
`$nnUNet_preprocessed/Dataset234_PETCT/` before running plan-and-preprocess,
or symlink it.

For complex inputs (PNG/RGB, MHA/NRRD, 3D TIFF, classification labels,
multi-modal with mismatched geometry, etc.) write your own splitter — the
shape is straightforward:

```python
import json
import random
from pathlib import Path

case_ids = sorted({
    p.name.rsplit("_", 1)[0]
    for p in Path("imagesTr").glob("*.nii.gz")
})

rng = random.Random(42)
rng.shuffle(case_ids)

num_folds = 5
splits = []
fold_size = len(case_ids) // num_folds
for fold in range(num_folds):
    start = fold * fold_size
    end = start + fold_size if fold < num_folds - 1 else len(case_ids)
    val = case_ids[start:end]
    train = [c for c in case_ids if c not in val]
    splits.append({"train": train, "val": val})

with open("splits_final.json", "w") as f:
    json.dump(splits, f, indent=2)
```

### Recording the seed

The seed used for splits **must** be recorded:

- In your `conversion_notes.md` Step 5 entry, under **Notes**, include the
  seed and `num_folds` used.
- Optionally, also include them in the `_manifest.json` (see below).

If you change the seed later, treat the dataset as a new dataset (bump
the ID) — never silently re-shuffle a dataset that has already been
trained against.

---

## Optional `_manifest.json` provenance companion

`conversion_notes.md` (Step 5) is **mandatory** and is for humans. The
`_manifest.json` described here is **optional** and is for tools — diffing
two builds of the same dataset, detecting silent file-list drift,
auditing licence/source fields programmatically.

**Both can coexist.** Run both, not one or the other.

### Location

```
$nnUNet_raw/Dataset<ID>_<Name>/_manifest.json
```

Sibling of `dataset.json`.

### Format

```json
{
  "dataset_name": "Dataset234_PETCT",
  "created": "2026-04-24T14:00:00Z",
  "source": {
    "type": "local_dicom",
    "path": "/home/user/raw_pet"
  },
  "num_files": 342,
  "file_checksum": "sha256:abc123...",
  "channels": ["CT", "PET"],
  "labels": {"0": "background", "1": "lesion"},
  "split_seed": 42,
  "num_folds": 5
}
```

`file_checksum` is a SHA-256 over the **sorted list of `(relative_path, size)`
tuples** under the dataset root, *not* over file contents. This is fast
even for WSI-scale data and still detects added/removed files and
size-changing edits.

### Generating it

```bash
python scripts/write_manifest.py \
    --dataset-dir $nnUNet_raw/Dataset234_PETCT \
    --source-type local_dicom \
    --source-path /home/user/raw_pet \
    --extra '{"channels": ["CT", "PET"], "split_seed": 42, "num_folds": 5}'
```

`--source-type` should be one of: `local_dicom`, `local_nifti`, `tcga_gdc`,
`kaggle`, `huggingface`, `gdrive`, or any other short identifier you use
consistently. Use the same vocabulary across all your datasets.

### When to regenerate

- After you add/remove cases.
- After you regenerate `splits_final.json` (record the new seed in
  `--extra`).
- Never edit `_manifest.json` by hand — re-run the script.

---

## Why both files?

| Concern | `conversion_notes.md` (mandatory) | `_manifest.json` (optional) |
|---|---|---|
| Audience | humans (you in 6 months, reviewers, collaborators) | tools (CI, diffs, audits) |
| Format | Markdown free-text + per-section template | Strict JSON, machine-validatable |
| Includes licence / paper / dropped files | yes (free-form) | no by default; pass via `--extra` |
| Detects silent file-list drift | no | yes (file-list checksum) |
| Required to skip Step 5? | **no — Step 5 is mandatory** | n/a |

If you only ever do one, do the markdown notes — that's the one that has
saved real datasets from being unreproducible.
