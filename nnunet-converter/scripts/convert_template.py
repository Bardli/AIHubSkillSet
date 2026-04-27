#!/usr/bin/env python3
"""
nnUNet v2 Dataset Conversion Template
======================================
Adapt this script to your specific input layout.
Run: python convert_to_nnunet.py

Core principle: AVOID UNNECESSARY FORMAT CONVERSION.
If your data is already in a supported format (.nii.gz, .mha, .nrrd, .png, .tif),
just copy/rename — do not convert to a different format.

Dependencies (install only what you need):
  pip install numpy Pillow          # for 2D PNG/BMP/TIFF
  pip install nibabel               # for NIfTI
  pip install SimpleITK             # for .mha/.nrrd or spatial resampling
"""

import os
import shutil
import json
import re
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================
# USER CONFIGURATION — edit these for your dataset
# ============================================================

INPUT_DIR = Path("/path/to/your/input/dataset")
OUTPUT_DIR = Path("/path/to/nnUNet_raw")

DATASET_ID = 42                        # 3-digit ID, avoid 001-010 (MSD reserved)
DATASET_NAME = "MyDataset"             # CamelCase, no spaces

# Channel definitions: channel_index -> (modality_name, glob_pattern_in_case_folder)
# For single modality: just one entry with index 0
# For multi-modal: add entries for each modality IN ORDER
# For RGB .png: just one entry (nnUNet reads 3 channels from single RGB file)
CHANNELS: Dict[int, Tuple[str, str]] = {
    0: ("CT", "image.nii.gz"),         # (nnunet_name, filename_pattern)
    # 1: ("T2", "t2.nii.gz"),          # uncomment for multi-modal
}

LABEL_FILENAME = "label.nii.gz"        # filename of the segmentation mask in each case folder

# Label mapping: {label_name: integer_value}
# 0 must always be background; values must be consecutive!
LABELS: Dict[str, int] = {
    "background": 0,
    "structure": 1,                    # rename to your actual structure
}

# Output file extension — USE THE SAME FORMAT AS YOUR INPUT when possible.
# Supported: .nii.gz, .mha, .nrrd, .png, .bmp, .tif
# IMPORTANT: .jpg is NOT supported (lossy). Convert .jpg inputs to .png.
FILE_ENDING = ".nii.gz"

# Train/test split — set TEST_RATIO = 0 to put everything in imagesTr
TEST_RATIO = 0.0                       # e.g. 0.2 means 20% go to imagesTs
RANDOM_SEED = 42

# Optional: force a specific ReaderWriter (usually not needed — nnUNet auto-detects)
# Options: "SimpleITKIO", "NibabelIO", "NibabelIOWithReorient", "NaturalImage2DIO", "Tiff3DIO"
OVERWRITE_READER_WRITER = None

# ============================================================
# HELPERS
# ============================================================

def copy_or_convert(src: Path, dst: Path):
    """
    Copy file if format matches FILE_ENDING, otherwise convert.
    For 2D: handles jpg->png conversion.
    For 3D: handles format conversion via SimpleITK.
    """
    src_ext = "".join(src.suffixes)
    if src_ext == FILE_ENDING:
        # Same format — just copy
        shutil.copy2(src, dst)
    elif src_ext in (".jpg", ".jpeg") and FILE_ENDING == ".png":
        # Lossy -> lossless conversion
        from PIL import Image
        img = Image.open(str(src))
        img.save(str(dst))
        print(f"  Converted (lossy->lossless): {src.name} -> {dst.name}")
    elif src_ext in (".png", ".bmp", ".tif", ".tiff") and FILE_ENDING in (".png", ".bmp", ".tif"):
        # 2D format conversion
        from PIL import Image
        img = Image.open(str(src))
        img.save(str(dst))
        print(f"  Converted: {src.name} -> {dst.name}")
    else:
        # 3D format conversion via SimpleITK
        import SimpleITK as sitk
        img = sitk.ReadImage(str(src))
        sitk.WriteImage(img, str(dst))
        print(f"  Converted: {src.name} -> {dst.name}")


def validate_labels(label_path: Path, expected_labels: Dict[str, int]) -> List[str]:
    """Check that label values are consecutive and match expectations. Returns warnings."""
    warnings = []

    suffix = "".join(label_path.suffixes)
    if suffix in (".png", ".bmp", ".tif", ".tiff"):
        from PIL import Image
        arr = np.array(Image.open(str(label_path)))
    else:
        import SimpleITK as sitk
        img = sitk.ReadImage(str(label_path))
        arr = sitk.GetArrayFromImage(img)

    unique_vals = sorted(np.unique(arr).astype(int).tolist())
    expected_vals = sorted(expected_labels.values())
    if unique_vals != expected_vals:
        warnings.append(
            f"  WARNING: {label_path.name} has labels {unique_vals}, "
            f"expected {expected_vals}"
        )

    # Check consecutive
    for i, v in enumerate(unique_vals):
        if v != i:
            warnings.append(
                f"  WARNING: Labels are not consecutive in {label_path.name}. "
                f"Found {unique_vals}. Remap before using nnUNet!"
            )
            break

    return warnings


def remap_labels(label_path: Path, mapping: Dict[int, int], output_path: Path):
    """Remap label integer values using a {old: new} mapping dict."""
    suffix = "".join(label_path.suffixes)
    if suffix in (".png", ".bmp", ".tif", ".tiff"):
        from PIL import Image
        arr = np.array(Image.open(str(label_path))).astype(np.int32)
        remapped = np.zeros_like(arr, dtype=np.uint8)
        for old_val, new_val in mapping.items():
            remapped[arr == old_val] = new_val
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(remapped).save(str(output_path))
    else:
        import SimpleITK as sitk
        img = sitk.ReadImage(str(label_path))
        arr = sitk.GetArrayFromImage(img).astype(np.int32)
        remapped = np.zeros_like(arr)
        for old_val, new_val in mapping.items():
            remapped[arr == old_val] = new_val
        out_img = sitk.GetImageFromArray(remapped)
        out_img.CopyInformation(img)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sitk.WriteImage(out_img, str(output_path))


# ============================================================
# LAYOUT DETECTION — adapt get_cases() for your input layout
# ============================================================

def get_cases() -> List[Path]:
    """
    Return list of case paths.

    LAYOUT A — per-subject subfolders (default):
        input/
          patient001/
            image.nii.gz
            label.nii.gz
          patient002/
            ...

    LAYOUT B — flat folders: edit to return list of case IDs
    instead, and adapt the copy logic in main() accordingly.
    """
    cases = sorted([p for p in INPUT_DIR.iterdir() if p.is_dir()])
    if not cases:
        raise RuntimeError(f"No subdirectories found in {INPUT_DIR}. "
                           "Edit get_cases() for your layout.")
    return cases


# ============================================================
# MAIN CONVERSION LOGIC
# ============================================================

def main():
    import random

    dataset_folder_name = f"Dataset{DATASET_ID:03d}_{DATASET_NAME}"
    dataset_root = OUTPUT_DIR / dataset_folder_name
    images_tr = dataset_root / "imagesTr"
    labels_tr = dataset_root / "labelsTr"
    images_ts = dataset_root / "imagesTs"

    images_tr.mkdir(parents=True, exist_ok=True)
    labels_tr.mkdir(parents=True, exist_ok=True)

    cases = get_cases()
    print(f"Found {len(cases)} cases in {INPUT_DIR}")

    # Train/test split
    random.seed(RANDOM_SEED)
    shuffled = cases[:]
    random.shuffle(shuffled)
    n_test = int(len(shuffled) * TEST_RATIO)
    test_cases = set(c.name for c in shuffled[:n_test])
    train_cases = [c for c in cases if c.name not in test_cases]

    if n_test > 0:
        images_ts.mkdir(parents=True, exist_ok=True)

    all_warnings = []
    n_train = 0

    for case_dir in cases:
        case_id = case_dir.name
        is_test = case_id in test_cases

        # --- Copy / convert each channel ---
        for ch_idx, (modality_name, ch_filename) in CHANNELS.items():
            src = case_dir / ch_filename
            if not src.exists():
                print(f"  SKIP: {src} not found")
                continue

            dst_name = f"{case_id}_{ch_idx:04d}{FILE_ENDING}"
            dst_dir = images_ts if is_test else images_tr
            dst = dst_dir / dst_name

            copy_or_convert(src, dst)

        # --- Copy label (train only) ---
        if not is_test:
            label_src = case_dir / LABEL_FILENAME
            if label_src.exists():
                label_dst = labels_tr / f"{case_id}{FILE_ENDING}"

                # Validate labels
                warnings = validate_labels(label_src, LABELS)
                all_warnings.extend(warnings)

                copy_or_convert(label_src, label_dst)
            else:
                print(f"  WARNING: No label found for {case_id}")
            n_train += 1

    # --- Generate dataset.json ---
    channel_names = {str(idx): name for idx, (name, _) in CHANNELS.items()}

    dataset_json = {
        "name": dataset_folder_name,
        "description": f"Converted by nnunet-converter skill",
        "channel_names": channel_names,
        "labels": LABELS,
        "numTraining": n_train,
        "file_ending": FILE_ENDING,
    }
    if OVERWRITE_READER_WRITER:
        dataset_json["overwrite_image_reader_writer"] = OVERWRITE_READER_WRITER

    json_path = dataset_root / "dataset.json"
    with open(json_path, "w") as f:
        json.dump(dataset_json, f, indent=4)

    # --- Summary ---
    print("\n" + "=" * 60)
    print(f"Conversion complete -> {dataset_root}")
    print(f"  Training cases : {n_train}")
    print(f"  Test cases     : {n_test}")
    print(f"  Channels       : {len(CHANNELS)}")
    print(f"  File ending    : {FILE_ENDING}")
    print(f"  dataset.json   : {json_path}")

    if all_warnings:
        print("\nWarnings (review before running nnUNet):")
        for w in all_warnings:
            print(w)
    else:
        print("\nNo label validation warnings.")

    print("\nNext steps:")
    print(f"  export nnUNet_raw={OUTPUT_DIR}")
    print(f"  nnUNetv2_plan_and_preprocess -d {DATASET_ID:03d} --verify_dataset_integrity")


if __name__ == "__main__":
    main()
