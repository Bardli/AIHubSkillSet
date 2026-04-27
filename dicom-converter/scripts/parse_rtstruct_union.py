#!/usr/bin/env python3
"""Iterate every *.dcm in an annotation directory, OR-union all RTSTRUCT ROIs,
and emit a JSON list of contours with SOP-UID anchors.

This is the bug-fix pattern from references/multi_rtstruct.md: many clinical
exporters emit one RTSTRUCT file per ROI in the annotation directory.
Reading only the first file silently drops N-1 ROIs (measured 10x undercount
on EAY131-8365856 acq2: 13929 vs 145642 voxels).

Example:
    python parse_rtstruct_union.py \\
        --annotation-dir /path/to/annotations \\
        --out contours.json

Optional ROI-name filtering (drop seed-point structures, etc.):
    python parse_rtstruct_union.py \\
        --annotation-dir /path/to/annotations \\
        --skip-roi-pattern "(?i)seed[ _-]?point" \\
        --out contours.json

Output JSON format:
    [
      {
        "rtstruct_file": "RT0001.dcm",
        "roi_number": 1,
        "roi_name": "Tumor",
        "contour_index": 0,
        "geometric_type": "CLOSED_PLANAR",
        "sop_uid": "1.3.6...",         # may be null when ContourImageSequence absent
        "n_points": 128,
        "points": [[x, y, z], ...]     # patient-coordinate triples
      },
      ...
    ]
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pydicom
except ImportError:
    print("ERROR: pydicom not installed. pip install pydicom", file=sys.stderr)
    sys.exit(2)


def parse_one_rtstruct(ds, source_filename, skip_pattern):
    """Yield contour dicts from a single RTSTRUCT dataset."""
    # Build ROI Number -> ROI Name map.
    roi_names = {}
    for sroi in getattr(ds, "StructureSetROISequence", []):
        try:
            roi_names[int(sroi.ROINumber)] = str(getattr(sroi, "ROIName", ""))
        except Exception:
            continue

    for roi in getattr(ds, "ROIContourSequence", []):
        try:
            roi_num = int(roi.ReferencedROINumber)
        except Exception:
            continue
        roi_name = roi_names.get(roi_num, "")
        if skip_pattern and skip_pattern.search(roi_name):
            continue
        for ci, contour in enumerate(getattr(roi, "ContourSequence", [])):
            cis = getattr(contour, "ContourImageSequence", None)
            sop_uid = None
            if cis:
                try:
                    sop_uid = str(cis[0].ReferencedSOPInstanceUID)
                except Exception:
                    sop_uid = None
            try:
                pts = list(map(float, contour.ContourData))
            except Exception:
                continue
            n_pts = len(pts) // 3
            if n_pts < 1:
                continue
            triples = [pts[i * 3 : i * 3 + 3] for i in range(n_pts)]
            yield {
                "rtstruct_file": source_filename,
                "roi_number": roi_num,
                "roi_name": roi_name,
                "contour_index": ci,
                "geometric_type": str(getattr(contour, "ContourGeometricType", "")),
                "sop_uid": sop_uid,
                "n_points": n_pts,
                "points": triples,
            }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--annotation-dir", required=True, help="Directory containing one or more RTSTRUCT *.dcm files")
    p.add_argument("--out", required=True, help="Output JSON path")
    p.add_argument(
        "--skip-roi-pattern",
        help='Regex; ROI names matching are skipped (e.g. "(?i)seed[ _-]?point" to drop seed structures)',
    )
    p.add_argument(
        "--require-sop-uid",
        action="store_true",
        help="Skip contours that do not have a ContourImageSequence anchor",
    )
    args = p.parse_args()

    ann_dir = Path(args.annotation_dir)
    if not ann_dir.is_dir():
        print(f"ERROR: {ann_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    skip_pattern = re.compile(args.skip_roi_pattern) if args.skip_roi_pattern else None

    rtstructs_seen = 0
    contours_total = 0
    contours_anchored = 0
    contours_unanchored = 0
    out = []

    for f in sorted(ann_dir.glob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() != ".dcm":
            continue
        try:
            ds = pydicom.dcmread(str(f))
        except (pydicom.errors.InvalidDicomError, IsADirectoryError):
            continue
        if getattr(ds, "Modality", None) != "RTSTRUCT":
            continue
        rtstructs_seen += 1
        for c in parse_one_rtstruct(ds, f.name, skip_pattern):
            contours_total += 1
            if c["sop_uid"]:
                contours_anchored += 1
            else:
                contours_unanchored += 1
                if args.require_sop_uid:
                    continue
            out.append(c)

    if rtstructs_seen == 0:
        print(f"ERROR: no RTSTRUCT *.dcm files found under {ann_dir}", file=sys.stderr)
        sys.exit(2)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f)

    pct_anchored = (100.0 * contours_anchored / contours_total) if contours_total else 0.0
    print(f"Wrote {out_path}")
    print(f"  RTSTRUCT files unioned: {rtstructs_seen}")
    print(f"  contours emitted: {len(out)}")
    print(f"  total contours seen:    {contours_total}")
    print(f"  SOP-UID anchored:       {contours_anchored}  ({pct_anchored:.1f}%)")
    print(f"  unanchored (fallback):  {contours_unanchored}")


if __name__ == "__main__":
    main()
