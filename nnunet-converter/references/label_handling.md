# Label Handling: Validation, Ignore Label, Region-Based Training

## Label validation

nnUNet requires:
- Label `0` = background (always). If there is no background concept, do **not** use `0` for something else.
- Consecutive integers: `0, 1, 2, 3, ...`
- No gaps (e.g. `0, 1, 4` is INVALID).
- Not all labels need to be present in every training case.

Check and remap if needed:

```python
import numpy as np
import nibabel as nib

img = nib.load("label.nii.gz")
data = img.get_fdata().astype(int)
unique_vals = sorted(np.unique(data))

# Remap to consecutive integers if needed
mapping = {old: new for new, old in enumerate(unique_vals)}
remapped = np.vectorize(mapping.get)(data).astype(np.uint8)
```

For 2D PNG masks, do the same remap and save with `PIL.Image.fromarray(remapped).save(...)`.

## Ignore label (sparse annotations)

nnUNet supports an `ignore` label for datasets with incomplete annotations (scribbles, partial slices, coarse masks). Regions marked with the ignore label are excluded from loss computation during training, but nnUNet still predicts dense segmentations at inference.

### Rules

- The ignore label **must** be the highest integer value in the segmentation.
- It **must** be named `"ignore"` in `dataset.json`.
- It is NOT predicted — do not include it in `regions_class_order`.

### Example

```json
"labels": {
    "background": 0,
    "edema": 1,
    "necrosis": 2,
    "enhancing_tumor": 3,
    "ignore": 4
}
```

### Use cases

- Scribble supervision (save annotation time)
- Dense annotation of only a subset of slices
- Masking out faulty regions in reference segmentations

## Region-based training (overlapping / hierarchical labels)

For tasks where evaluation targets are overlapping regions rather than individual labels (e.g., BraTS: whole tumor, tumor core, enhancing tumor), nnUNet supports region-based training.

### How it works

- Labels in `dataset.json` are declared as **lists of integers** representing which raw label values belong to that region.
- An additional `regions_class_order` field tells nnUNet how to convert regions back to an integer segmentation map.
- nnU-Net trains on regions and evaluates on regions.

### Example (BraTS-style)

Standard label-based:
```json
"labels": {
    "background": 0,
    "edema": 1,
    "non_enhancing_and_necrosis": 2,
    "enhancing_tumor": 3
}
```

Region-based equivalent:
```json
"labels": {
    "background": 0,
    "whole_tumor": [1, 2, 3],
    "tumor_core": [2, 3],
    "enhancing_tumor": 3
},
"regions_class_order": [1, 2, 3]
```

### Critical rules

- `regions_class_order` length must equal the number of regions (excluding background).
- **Order matters**: encompassing regions first, substructures later (later entries overwrite earlier ones).
- **IMPORTANT**: when writing `dataset.json`, use `sort_keys=False` in `json.dump()` to preserve label declaration order.
- Compatible with the ignore label — just do not include `ignore` in `regions_class_order`.

## Common pitfalls

- Storing masks as float (e.g. `.0`, `.5`) — cast to `uint8`/`uint16` integers before saving.
- Using `255` as foreground in PNG masks — must be remapped to `1`.
- Sorting label keys alphabetically when writing dataset.json — breaks region-based training; pass `sort_keys=False`.
- Forgetting that the `ignore` label must be the highest integer.
