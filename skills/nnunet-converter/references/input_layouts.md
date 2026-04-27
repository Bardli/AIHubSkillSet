# Common Input Dataset Layouts

Real-world segmentation datasets show up in a small number of recognizable layouts. Identify which one you have **before** writing the conversion script — it determines how cases are paired and how channels are detected.

## Layout A: Two flat folders (`images/` and `labels/`)

```
input/
├── images/
│   ├── patient001.nii.gz
│   └── patient002.nii.gz
└── labels/
    ├── patient001.nii.gz
    └── patient002.nii.gz
```

**Strategy:** Sort both folders. Pair by sorted index or by matching filename stem. Use the stem as the case ID.

## Layout B: Per-subject folders

```
input/
├── patient001/
│   ├── T1.nii.gz
│   ├── T2.nii.gz
│   └── seg.nii.gz
└── patient002/
    ├── T1.nii.gz
    ├── T2.nii.gz
    └── seg.nii.gz
```

**Strategy:** Walk subdirectories. Use the folder name as the case ID. Detect channels by known filenames (e.g. `T1.nii.gz` → channel 0, `T2.nii.gz` → channel 1) using a fixed mapping that you apply consistently to every case.

## Layout C: Single folder with mixed image/label files

```
input/
├── patient001_image.nii.gz
├── patient001_label.nii.gz
├── patient002_image.nii.gz
└── patient002_label.nii.gz
```

**Strategy:** Use a regex / glob pattern to separate images from labels by suffix (`_image` vs `_label`). Strip the suffix to get the case ID.

## Layout D: 2D images organized by class folder + separate masks

```
input/
├── train/
│   ├── ClassA/
│   │   ├── img001.png
│   │   └── img002.png
│   └── ClassB/
│       ├── img003.png
│       └── img004.png
└── masks/
    ├── img001.png
    └── img002.png
```

**Strategy:** Walk class folders for images. The folder name yields a **classification label** for each case (write to `cls_data.csv`). Match images to masks by filename stem.

## How to choose your strategy

1. List the top two levels of the input directory (`ls`, `find -maxdepth 2`).
2. Match against the four layouts above. Most real datasets are exactly one of these or a small variation.
3. Build a deterministic case-ID derivation rule. The same input file must always produce the same case ID across re-runs.
4. Verify image–label pairing **before** copying any file: print the first 5 pairs and confirm visually.
