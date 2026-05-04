#!/usr/bin/env python3
"""Generate image + label overlay QC videos for nnU-Net-style 3D datasets.

Default input layout:
    DatasetXXX_Name/
      imagesTr/case_001_0000.nii.gz
      labelsTr/case_001.nii.gz

Examples:
    python make_overlay_qc_videos.py --dataset-dir /path/to/Dataset123_Liver --output-dir qc_videos
    python make_overlay_qc_videos.py --dataset-dir /path/to/Dataset123_Liver --case-id case_001 --output-dir qc_videos
    python make_overlay_qc_videos.py --images-dir imagesTr --labels-dir labelsTr --channel 1 --num-samples 10 --output-dir qc_videos
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


SUPPORTED_EXTS = (".nii.gz", ".mha", ".nrrd")
VIVID_COLORS = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (255, 0, 255),
    (0, 255, 255),
    (255, 128, 0),
    (128, 0, 255),
    (0, 128, 255),
    (128, 255, 0),
    (255, 0, 128),
    (0, 255, 128),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate per-case MP4 overlay videos from 3D imagesTr/labelsTr volumes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset-dir", type=Path, help="Dataset root containing imagesTr/ and labelsTr/.")
    parser.add_argument("--images-dir", type=Path, help="Directory containing nnU-Net channel-suffixed images.")
    parser.add_argument("--labels-dir", type=Path, help="Directory containing nnU-Net labels.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for output MP4 videos.")
    parser.add_argument("--num-samples", type=int, default=5, help="Random cases to render when --case-id is omitted.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling.")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Explicit case ID to render. Repeat or comma-separate for multiple cases. Overrides random sampling.",
    )
    parser.add_argument("--channel", type=int, default=0, help="nnU-Net image channel to render, e.g. 0 for _0000.")
    parser.add_argument(
        "--modality",
        choices=("generic", "CT"),
        default="generic",
        help="generic uses percentile normalization; CT uses window-level/window-width.",
    )
    parser.add_argument("--window-level", type=float, default=40.0, help="CT window level used with --modality CT.")
    parser.add_argument("--window-width", type=float, default=400.0, help="CT window width used with --modality CT.")
    parser.add_argument("--alpha", type=float, default=0.45, help="Mask overlay opacity.")
    parser.add_argument("--fps", type=float, default=5.0, help="Output video frames per second.")
    parser.add_argument("--max-size", type=int, default=512, help="Resize each panel so its longest side is at most this.")
    parser.add_argument(
        "--crop-to-label",
        action="store_true",
        help="Render only label-containing slices plus --margin-slices. Default renders every slice.",
    )
    parser.add_argument("--margin-slices", type=int, default=6, help="Context slices when --crop-to-label is set.")
    return parser.parse_args()


def known_ext(path: Path) -> Optional[str]:
    name = path.name.lower()
    for ext in SUPPORTED_EXTS:
        if name.endswith(ext):
            return ext
    return None


def remove_known_ext(path: Path) -> str:
    ext = known_ext(path)
    if ext is None:
        return path.stem
    return path.name[: -len(ext)]


def resolve_dirs(args: argparse.Namespace) -> Tuple[Path, Path]:
    images_dir = args.images_dir
    labels_dir = args.labels_dir
    if args.dataset_dir is not None:
        images_dir = images_dir or args.dataset_dir / "imagesTr"
        labels_dir = labels_dir or args.dataset_dir / "labelsTr"
    if images_dir is None or labels_dir is None:
        raise SystemExit("ERROR: provide --dataset-dir or both --images-dir and --labels-dir")
    if not images_dir.is_dir():
        raise SystemExit(f"ERROR: images directory not found: {images_dir}")
    if not labels_dir.is_dir():
        raise SystemExit(f"ERROR: labels directory not found: {labels_dir}")
    return images_dir, labels_dir


def discover_cases(images_dir: Path, labels_dir: Path, channel: int) -> Dict[str, Tuple[Path, Path]]:
    suffix = f"_{channel:04d}"
    cases = {}  # type: Dict[str, Tuple[Path, Path]]
    for image_path in sorted(p for p in images_dir.iterdir() if p.is_file() and known_ext(p)):
        base = remove_known_ext(image_path)
        if not base.endswith(suffix):
            continue
        case_id = base[: -len(suffix)]
        label_path = find_label(labels_dir, case_id)
        if label_path is not None:
            cases[case_id] = (image_path, label_path)
    return cases


def find_label(labels_dir: Path, case_id: str) -> Optional[Path]:
    for ext in SUPPORTED_EXTS:
        candidate = labels_dir / f"{case_id}{ext}"
        if candidate.is_file():
            return candidate
    return None


def normalize_image(volume: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    volume = volume.astype(np.float32)
    if args.modality == "CT":
        lower = args.window_level - args.window_width / 2.0
        upper = args.window_level + args.window_width / 2.0
        clipped = np.clip(volume, lower, upper)
        return ((clipped - lower) / max(upper - lower, 1e-6) * 255.0).astype(np.uint8)

    finite = volume[np.isfinite(volume)]
    if finite.size == 0:
        return np.zeros_like(volume, dtype=np.uint8)
    nonzero = finite[finite != 0]
    values = nonzero if nonzero.size else finite
    p1, p99 = np.percentile(values, [1, 99])
    if p99 <= p1:
        return np.zeros_like(volume, dtype=np.uint8)
    clipped = np.clip(volume, p1, p99)
    return ((clipped - p1) / (p99 - p1) * 255.0).astype(np.uint8)


def as_zyx(array: np.ndarray) -> np.ndarray:
    if array.ndim == 2:
        return array[None, :, :]
    if array.ndim == 3:
        return array
    raise ValueError(f"expected 2D or 3D image, got shape {array.shape}")


def slice_indices(label: np.ndarray, crop_to_label: bool, margin: int) -> range:
    depth = label.shape[0]
    if not crop_to_label or not np.any(label > 0):
        return range(depth)
    z_values = np.where(label > 0)[0]
    start = max(int(z_values.min()) - margin, 0)
    stop = min(int(z_values.max()) + margin + 1, depth)
    return range(start, stop)


def resize_panel(panel: np.ndarray, max_size: int, cv2) -> np.ndarray:
    height, width = panel.shape[:2]
    longest = max(height, width)
    if max_size <= 0 or longest <= max_size:
        return panel
    scale = max_size / float(longest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(panel, new_size, interpolation=cv2.INTER_AREA)


def overlay_mask(gray_rgb: np.ndarray, mask: np.ndarray, alpha: float, cv2) -> np.ndarray:
    out = gray_rgb.copy()
    labels = [int(v) for v in np.unique(mask) if v != 0]
    for idx, label_value in enumerate(labels):
        color = np.array(VIVID_COLORS[idx % len(VIVID_COLORS)], dtype=np.uint8)
        mask_idx = mask == label_value
        if not np.any(mask_idx):
            continue
        color_layer = np.zeros_like(out, dtype=np.uint8)
        color_layer[:, :] = color
        blended = cv2.addWeighted(out, 1.0 - alpha, color_layer, alpha, 0)
        out[mask_idx] = blended[mask_idx]

        binary = mask_idx.astype(np.uint8)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, (255, 255, 255), 1)
    return out


def make_frame(gray_slice: np.ndarray, label_slice: np.ndarray, header: str, args: argparse.Namespace, cv2) -> np.ndarray:
    gray_rgb = cv2.cvtColor(gray_slice, cv2.COLOR_GRAY2BGR)
    overlay = overlay_mask(gray_rgb, label_slice, args.alpha, cv2)
    left = resize_panel(gray_rgb, args.max_size, cv2)
    right = resize_panel(overlay, args.max_size, cv2)
    if left.shape[:2] != right.shape[:2]:
        right = cv2.resize(right, (left.shape[1], left.shape[0]), interpolation=cv2.INTER_AREA)
    body = np.concatenate([left, right], axis=1)
    header_h = 40
    canvas = np.zeros((body.shape[0] + header_h, body.shape[1], 3), dtype=np.uint8)
    canvas[:header_h, :] = (30, 30, 30)
    canvas[header_h:, :] = body
    cv2.putText(canvas, header[:120], (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (245, 245, 245), 1, cv2.LINE_AA)
    return canvas


def read_volume(path: Path, sitk) -> np.ndarray:
    image = sitk.ReadImage(str(path))
    return as_zyx(sitk.GetArrayFromImage(image))


def write_case_video(case_id: str, image_path: Path, label_path: Path, out_dir: Path, args: argparse.Namespace) -> Path:
    try:
        import cv2
        import SimpleITK as sitk
    except ImportError as exc:
        raise SystemExit(
            "ERROR: missing dependency. Install SimpleITK and opencv-python to generate videos."
        ) from exc

    image = read_volume(image_path, sitk)
    label = read_volume(label_path, sitk)
    if image.shape != label.shape:
        raise ValueError(f"{case_id}: image shape {image.shape} != label shape {label.shape}")

    image_u8 = normalize_image(image, args)
    z_iter = list(slice_indices(label, args.crop_to_label, args.margin_slices))
    if not z_iter:
        raise ValueError(f"{case_id}: no slices selected")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{case_id}_ch{args.channel:04d}.mp4"
    writer = None
    try:
        for z in z_iter:
            header = f"{case_id} | channel {args.channel:04d} | slice {z + 1}/{image.shape[0]} | label voxels {(label[z] > 0).sum()}"
            frame = make_frame(image_u8[z], label[z], header, args, cv2)
            if writer is None:
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(out_path), fourcc, args.fps, (frame.shape[1], frame.shape[0]))
                if not writer.isOpened():
                    raise RuntimeError(f"could not open video writer for {out_path}")
            writer.write(frame)
    finally:
        if writer is not None:
            writer.release()
    return out_path


def parse_case_ids(values: List[str]) -> List[str]:
    case_ids = []  # type: List[str]
    for value in values:
        case_ids.extend(part.strip() for part in value.split(",") if part.strip())
    return case_ids


def choose_cases(all_cases: Dict[str, Tuple[Path, Path]], args: argparse.Namespace) -> List[str]:
    explicit = parse_case_ids(args.case_id)
    if explicit:
        missing = [case_id for case_id in explicit if case_id not in all_cases]
        if missing:
            raise SystemExit(f"ERROR: requested case IDs not found for channel {args.channel}: {', '.join(missing)}")
        return explicit
    if args.num_samples < 1:
        raise SystemExit("ERROR: --num-samples must be >= 1")
    case_ids = sorted(all_cases)
    rng = random.Random(args.seed)
    rng.shuffle(case_ids)
    return case_ids[: min(args.num_samples, len(case_ids))]


def main() -> int:
    args = parse_args()
    images_dir, labels_dir = resolve_dirs(args)
    cases = discover_cases(images_dir, labels_dir, args.channel)
    if not cases:
        raise SystemExit(f"ERROR: no image/label pairs found for channel {args.channel} in {images_dir} and {labels_dir}")

    selected = choose_cases(cases, args)
    print(f"Rendering {len(selected)} case(s): {', '.join(selected)}")
    for case_id in selected:
        image_path, label_path = cases[case_id]
        out_path = write_case_video(case_id, image_path, label_path, args.output_dir, args)
        print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
