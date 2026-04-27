#!/usr/bin/env python3
"""Build a SOP-UID -> AcquisitionNumber map from a CT/MR series directory.

This is the foundation step for SOP-UID-anchored annotation routing — see
references/sop_uid_routing.md. Run this once per series, persist the JSON,
and pass it to any rasterizer that needs to route RTSTRUCT contours or SEG
frames to the correct acquisition.

CRITICAL: build the map from the FULL per-acquisition file list, not from a
z-deduped subset. A z-dedup that prunes the map silently re-introduces
nearest-z fallback for any duplicate-z slice (the EAY131 V6 dedup bug,
patched 2026-04-26).

Example:
    python build_sop_to_acq.py --series /path/to/ct_dir --out sop_to_acq.json
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import pydicom
except ImportError:
    print("ERROR: pydicom not installed. pip install pydicom", file=sys.stderr)
    sys.exit(2)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--series", required=True, help="CT/MR series directory")
    p.add_argument("--out", required=True, help="Output JSON path")
    p.add_argument(
        "--modalities",
        nargs="+",
        default=["CT", "MR"],
        help="Modalities to include (default: CT MR)",
    )
    p.add_argument(
        "--filter-localizer",
        action="store_true",
        help="Drop files with 'LOCALIZER' in ImageType",
    )
    args = p.parse_args()

    series_dir = Path(args.series)
    if not series_dir.is_dir():
        print(f"ERROR: {series_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    sop_to_acq = {}
    by_acq = {}
    n_skipped_localizer = 0
    n_skipped_modality = 0

    for f in sorted(series_dir.rglob("*")):
        if not f.is_file():
            continue
        try:
            ds = pydicom.dcmread(str(f), stop_before_pixels=True, force=True)
        except Exception:
            continue
        mod = getattr(ds, "Modality", None)
        if mod not in args.modalities:
            n_skipped_modality += 1
            continue
        if args.filter_localizer:
            it = tuple(getattr(ds, "ImageType", []))
            if "LOCALIZER" in it:
                n_skipped_localizer += 1
                continue
        sop_uid = getattr(ds, "SOPInstanceUID", None)
        if not sop_uid:
            continue
        acq = int(getattr(ds, "AcquisitionNumber", 1))
        sop_to_acq[sop_uid] = acq
        by_acq.setdefault(acq, 0)
        by_acq[acq] += 1

    if not sop_to_acq:
        print("ERROR: no SOP-UID-bearing files found. Check --modalities.", file=sys.stderr)
        sys.exit(2)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(sop_to_acq, f)

    print(f"Wrote {out_path}")
    print(f"  unique SOP UIDs: {len(sop_to_acq)}")
    print(f"  acquisitions: {sorted(by_acq.items())}")
    if args.filter_localizer:
        print(f"  skipped (LOCALIZER):  {n_skipped_localizer}")
    print(f"  skipped (other modality): {n_skipped_modality}")


if __name__ == "__main__":
    main()
