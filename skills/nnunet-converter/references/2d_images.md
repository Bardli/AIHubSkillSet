# 2D Image Datasets (PNG / BMP / TIFF)

nnUNet v2 natively supports 2D images via `NaturalImage2DIO`.
**Do NOT wrap 2D images in NIfTI containers.**

Supported 2D extensions: `.png`, `.bmp`, `.tif`.
JPEG (`.jpg` / `.jpeg`) is **forbidden** (lossy). If the source is JPEG, convert to PNG.

## RGB natural images (endoscopy, dermoscopy, surgical, etc.)

RGB images are stored as a **single** `.png` file per case. nnUNet reads the 3 channels automatically — do **NOT** split RGB into 3 separate channel files.

```python
from PIL import Image

# RGB: save as a single PNG — do NOT split into 3 separate channel files
img = Image.open("input.jpg").convert("RGB")
img.save("imagesTr/case_001_0000.png")  # single file, _0000 suffix

# Mask: save as single-channel PNG with integer label values
mask = Image.open("mask.png")
mask.save("labelsTr/case_001.png")  # no channel suffix
```

`dataset.json` for RGB:
```json
{
  "channel_names": {"0": "R", "1": "G", "2": "B"},
  "labels": {"background": 0, "tumor": 1},
  "numTraining": 500,
  "file_ending": ".png"
}
```

> **Note:** Even though `channel_names` lists 3 channels, the image is stored as a single RGB `.png` file with only the `_0000` suffix. This is the sole exception to the one-file-per-channel rule.

## Grayscale 2D images (ultrasound, X-ray, etc.)

```python
from PIL import Image

img = Image.open("input.png").convert("L")
img.save("imagesTr/case_001_0000.png")
```

`dataset.json` for grayscale:
```json
{
  "channel_names": {"0": "Ultrasound"},
  "labels": {"background": 0, "lesion": 1},
  "numTraining": 200,
  "file_ending": ".png"
}
```

## Common pitfalls

- Splitting RGB into 3 separate `_0000`/`_0001`/`_0002` files — wrong, use a single RGB PNG.
- Wrapping 2D PNG/BMP into `.nii.gz` "for safety" — wrong, breaks the natural image reader path.
- Mixing `.png` and `.bmp` in one dataset — pick one `file_ending` and use it for every file.
- Saving masks with anti-aliased smoothing (e.g. JPEG masks) — masks must be lossless integer PNG.
