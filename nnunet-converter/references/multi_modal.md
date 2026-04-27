# Multi-Modal Handling and Spatial Resampling

## Multi-modal layout

For multi-modal MRI (e.g. T1, T2, FLAIR):
- Each modality becomes a separate file with an incrementing channel index.
- Channel order must be **identical** for all cases.
- `channel_names` in `dataset.json` maps `"0"` → `"T1"`, `"1"` → `"T2"`, etc.

Example output for 4-channel BraTS-style data:
```
imagesTr/
├── BraTS_001_0000.nii.gz   # T1
├── BraTS_001_0001.nii.gz   # T1Gd
├── BraTS_001_0002.nii.gz   # T2
├── BraTS_001_0003.nii.gz   # FLAIR
└── ...
```

```json
{
  "channel_names": {"0": "T1", "1": "T1Gd", "2": "T2", "3": "FLAIR"},
  "labels": {"background": 0, "edema": 1, "non_enh_necrosis": 2, "enh_tumor": 3},
  "numTraining": 369,
  "file_ending": ".nii.gz"
}
```

## Spatial resampling

When combining modalities with **different spatial resolutions** (common in MRI), all channels must be resampled to a common reference space before nnUNet can use them.

### When to resample

- Check `size`, `spacing`, `origin`, and `direction` of each modality.
- If any differ across modalities of the same case, resample the non-reference modalities to match the reference.
- The reference is usually the **highest-resolution** modality (preserves detail) or a designated anatomical reference (e.g. T2W in PI-CAI).

### How to resample

```python
import SimpleITK as sitk

def resample_to_reference(moving_img, reference_img, interpolator=sitk.sitkLinear):
    """Resample moving image to match reference image geometry."""
    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(reference_img)
    resampler.SetInterpolator(interpolator)
    resampler.SetDefaultPixelValue(0)
    return resampler.Execute(moving_img)
```

### Interpolation choice

- **Images**: `sitk.sitkLinear` (smooth, preserves intensity gradients)
- **Labels / masks**: `sitk.sitkNearestNeighbor` (preserves integer label values — never use linear on labels)

### Example: PICAI dataset

- T2W: 384×384×19 @ 0.5 mm — high-res reference
- ADC: 84×128×19 @ 2.0 mm → resample to T2W space
- HBV: 84×128×19 @ 2.0 mm → resample to T2W space
- Labels: already at T2W resolution

## Common pitfalls

- Resampling labels with linear interpolation — produces fractional values; use nearest-neighbor.
- Forgetting to verify spacing/origin equality after resampling — sanity check with `sitk.GetArrayFromImage(...).shape` and metadata.
- Using different reference images for different cases — pick a consistent rule and apply it to every case.
