#!/usr/bin/env python3
"""Format a directory of NIfTI images + masks into an nnUNetv2 dataset.

This is the **simple-case** converter. Use it ONLY when:
- Inputs are 3D NIfTI (`.nii.gz`).
- Per-case layout is exactly:
      raw-dir/images/<case>_<chan>.nii.gz
      raw-dir/labels/<case>.nii.gz
- Labels are already contiguous integers starting at 0.
- All cases have the same channel set.

For anything more complex (PNG/RGB, MHA/NRRD, 3D TIFF, multi-modal with
mismatched geometry, label remapping, ignore label, region-based labels,
classification labels), do NOT use this script — write a custom converter
based on `convert_template.py` instead. Read the relevant
`references/*.md` first, as required by SKILL.md.

Adapted from https://github.com/ryanwangk/medimg_skills (MIT).

Expected input layout:
    raw-dir/
        images/
            case001_0000.nii.gz     # modality 0
            case001_0001.nii.gz     # modality 1 (if multi-channel)
            case002_0000.nii.gz
            ...
        labels/
            case001.nii.gz
            case002.nii.gz
            ...

Produces:
    <output-root>/Dataset<ID>_<Name>/
        imagesTr/
        labelsTr/
        dataset.json
        splits_final.json  (patient-level, seeded — see references/splits_and_provenance.md)

Example:
    python make_nnunet_dataset_simple.py --raw-dir ./raw --dataset-id 234 \\
        --dataset-name PETCT --channels CT PET \\
        --labels "background,lesion" --output-root $nnUNet_raw
"""
import argparse
import json
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw-dir", required=True, help="Dir with images/ and labels/ subdirs")
    p.add_argument("--dataset-id", type=int, required=True, help="3-digit nnUNet dataset id")
    p.add_argument("--dataset-name", required=True, help="Short dataset name, e.g. PETCT")
    p.add_argument("--channels", nargs="+", required=True, help='Channel names in order, e.g. CT PET')
    p.add_argument("--labels", required=True, help='Comma-separated labels, background first. e.g. "background,lesion,edema"')
    p.add_argument("--output-root", required=True, help="Parent dir (usually $nnUNet_raw)")
    p.add_argument("--file-ending", default=".nii.gz")
    p.add_argument("--split-seed", type=int, default=42)
    p.add_argument("--num-folds", type=int, default=5)
    args = p.parse_args()

    raw = Path(args.raw_dir)
    images_dir = raw / "images"
    labels_dir = raw / "labels"
    if not images_dir.is_dir() or not labels_dir.is_dir():
        print(f"ERROR: expected {images_dir} and {labels_dir} to exist", file=sys.stderr)
        sys.exit(1)

    # Group images by case id
    cases = defaultdict(dict)
    for img in sorted(images_dir.glob(f"*{args.file_ending}")):
        stem = img.name[:-len(args.file_ending)]
        if "_" not in stem:
            print(f"WARNING: skipping {img.name} (expected <case>_<channel>{args.file_ending})", file=sys.stderr)
            continue
        case_id, chan = stem.rsplit("_", 1)
        try:
            chan_idx = int(chan)
        except ValueError:
            print(f"WARNING: skipping {img.name} (channel suffix not numeric)", file=sys.stderr)
            continue
        cases[case_id][chan_idx] = img

    if not cases:
        print("ERROR: no cases found", file=sys.stderr)
        sys.exit(1)

    expected_channels = set(range(len(args.channels)))
    valid_cases = []
    for case_id, chans in sorted(cases.items()):
        if set(chans.keys()) != expected_channels:
            print(f"WARNING: {case_id} has channels {sorted(chans.keys())}, expected {sorted(expected_channels)}. Skipping.", file=sys.stderr)
            continue
        label = labels_dir / f"{case_id}{args.file_ending}"
        if not label.exists():
            print(f"WARNING: {case_id} has no label at {label}. Skipping.", file=sys.stderr)
            continue
        valid_cases.append((case_id, chans, label))

    if not valid_cases:
        print("ERROR: no valid cases after filtering", file=sys.stderr)
        sys.exit(1)

    # Build dataset dir
    ds_name = f"Dataset{args.dataset_id:03d}_{args.dataset_name}"
    out = Path(args.output_root) / ds_name
    (out / "imagesTr").mkdir(parents=True, exist_ok=True)
    (out / "labelsTr").mkdir(parents=True, exist_ok=True)

    for case_id, chans, label in valid_cases:
        for chan_idx, img_path in chans.items():
            dest = out / "imagesTr" / f"{case_id}_{chan_idx:04d}{args.file_ending}"
            shutil.copy2(img_path, dest)
        shutil.copy2(label, out / "labelsTr" / f"{case_id}{args.file_ending}")

    # dataset.json
    label_names = [l.strip() for l in args.labels.split(",")]
    labels_dict = {name: idx for idx, name in enumerate(label_names)}
    channel_names = {str(i): name for i, name in enumerate(args.channels)}

    dataset_json = {
        "channel_names": channel_names,
        "labels": labels_dict,
        "numTraining": len(valid_cases),
        "file_ending": args.file_ending,
    }
    with open(out / "dataset.json", "w") as f:
        json.dump(dataset_json, f, indent=2)

    # Patient-level splits
    rng = random.Random(args.split_seed)
    case_ids = [c[0] for c in valid_cases]
    rng.shuffle(case_ids)

    splits = []
    fold_size = len(case_ids) // args.num_folds
    for fold in range(args.num_folds):
        start = fold * fold_size
        end = start + fold_size if fold < args.num_folds - 1 else len(case_ids)
        val = case_ids[start:end]
        train = [c for c in case_ids if c not in val]
        splits.append({"train": train, "val": val})
    with open(out / "splits_final.json", "w") as f:
        json.dump(splits, f, indent=2)

    print(f"Wrote {ds_name} with {len(valid_cases)} cases to {out}")
    print(f"  channels: {args.channels}")
    print(f"  labels: {labels_dict}")
    print(f"  {args.num_folds}-fold splits seeded with {args.split_seed}")


if __name__ == "__main__":
    main()
