# 3D TIFF Datasets

For 3D TIFF stacks (e.g., microscopy, OCT), nnUNet uses `Tiff3DIO`. This includes **multi-frame TIFFs** (e.g., ImageJ stacks) — they are 3D volumes and Tiff3DIO handles them natively. Do **NOT** convert multi-frame TIFFs to `.nii.gz`.

## Companion .json with spacing

Each `.tif` file must have a companion `.json` file (same name, **without** the channel suffix) with spacing information:

```json
{
    "spacing": [7.6, 7.6, 80.0]
}
```

If the data has no real-world spacing (e.g., OCT), use `[1.0, 1.0, 1.0]` as a placeholder.

## Folder structure

```
Dataset123_Foo/
├── dataset.json
├── imagesTr/
│   ├── cell6_0000.tif
│   └── cell6.json         # spacing info for cell6 (no channel suffix on json)
└── labelsTr/
    ├── cell6.tif
    └── cell6.json         # spacing info for cell6
```

Set `"overwrite_image_reader_writer": "Tiff3DIO"` in `dataset.json` to ensure nnUNet uses the correct reader.

## Code

```python
import shutil
import json
import tifffile
import numpy as np

spacing = [1.0, 1.0, 1.0]  # replace with real spacing if known

# Images: copy .tif as-is, add companion .json
shutil.copy2("input/OCT001.tif", "imagesTr/OCT001_0000.tif")
with open("imagesTr/OCT001.json", "w") as f:
    json.dump({"spacing": spacing}, f)

# Masks: remap values if needed, write as .tif, add companion .json
mask = tifffile.imread("input/OCT001_mask.tif").astype(np.uint8)
mask[mask == 255] = 1  # remap to consecutive labels
tifffile.imwrite("labelsTr/OCT001.tif", mask)
with open("labelsTr/OCT001.json", "w") as f:
    json.dump({"spacing": spacing}, f)
```

## dataset.json for 3D TIFF

```json
{
  "channel_names": {"0": "OCT"},
  "labels": {"background": 0, "lesion": 1},
  "numTraining": 100,
  "file_ending": ".tif",
  "overwrite_image_reader_writer": "Tiff3DIO"
}
```

## Common pitfalls

- Forgetting the companion `.json` — Tiff3DIO will fail to load without spacing.
- Putting the channel suffix on the companion json (`cell6_0000.json`) — wrong, the json name omits `_0000`.
- Converting multi-frame TIFF to `.nii.gz` "to standardize" — never needed, Tiff3DIO is native.
