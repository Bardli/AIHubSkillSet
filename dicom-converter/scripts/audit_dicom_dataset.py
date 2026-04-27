#!/usr/bin/env python3
"""Header-only audit of a DICOM dataset against the 10 cleanliness checks.

Implements the audit table in references/audit_checklist.md. Walks every
series directory under --root, runs all 10 checks header-only
(pydicom.dcmread(stop_before_pixels=True)), and reports clean vs dirty.

Exit codes:
    0  all series clean (no red flags)
    1  at least one series has a red flag (dirty)
    2  hard error (e.g., unreadable directory)

Examples:
    # Audit a single series directory
    python audit_dicom_dataset.py --series /path/to/dicom_series

    # Audit every series directory under a root, write a CSV report
    python audit_dicom_dataset.py --root /path/to/dataset \\
        --csv audit_report.csv

    # Just the summary, exit code only
    python audit_dicom_dataset.py --root /path/to/dataset --quiet
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

try:
    import numpy as np
    import pydicom
except ImportError as e:
    print(f"ERROR: missing dependency: {e.name}. pip install pydicom numpy", file=sys.stderr)
    sys.exit(2)


CHECKS = [
    "z_spacing_uniform",
    "single_acquisition",
    "no_duplicate_z",
    "consistent_orientation",
    "annotation_anchored",
    "single_rtstruct",
    "single_modality",
    "slice_thickness_matches_z_gap",
    "no_localizer",
    "rtstruct_for_uid_match",
]


def read_header(path):
    try:
        return pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
    except Exception:
        return None


def list_dicoms(directory):
    return [p for p in sorted(directory.rglob("*")) if p.is_file()]


def audit_series(series_dir):
    """Run all 10 checks on a single series-like directory.

    The directory may contain a CT series, an annotation directory (RTSTRUCT
    or SEG), or both. We classify files by Modality and run the relevant checks.
    """
    files = list_dicoms(series_dir)
    if not files:
        return {"series": str(series_dir), "error": "no files"}

    # Read every header (header-only is fast).
    headers = []
    for f in files:
        ds = read_header(f)
        if ds is None:
            continue
        headers.append((f, ds))

    if not headers:
        return {"series": str(series_dir), "error": "no readable DICOM"}

    # Bucket by Modality.
    by_modality = defaultdict(list)
    for f, ds in headers:
        mod = getattr(ds, "Modality", "?")
        by_modality[mod].append((f, ds))

    result = {"series": str(series_dir), "n_files": len(headers), "modalities": sorted(by_modality)}

    # Check 7 — single Modality
    result["single_modality"] = len(by_modality) <= 1

    # Use the largest image-modality bucket for image checks
    image_mods = [m for m in by_modality if m in {"CT", "MR", "PT", "OT"}]
    if not image_mods:
        # Pure annotation dir: still run annotation checks only
        ct_headers = []
    else:
        # Pick the modality with the most files
        primary = max(image_mods, key=lambda m: len(by_modality[m]))
        ct_headers = by_modality[primary]

    # --- Image-stack checks ---
    if ct_headers:
        zs = []
        ipps = []
        iops = []
        acqs = []
        thicknesses = []
        image_types = []
        for _, ds in ct_headers:
            try:
                ipp = [float(x) for x in ds.ImagePositionPatient]
            except Exception:
                continue
            zs.append(ipp[2])
            ipps.append(ipp)
            try:
                iops.append(tuple(round(float(x), 4) for x in ds.ImageOrientationPatient))
            except Exception:
                pass
            try:
                acqs.append(int(getattr(ds, "AcquisitionNumber", 1)))
            except Exception:
                acqs.append(1)
            try:
                thicknesses.append(float(ds.SliceThickness))
            except Exception:
                pass
            try:
                image_types.append(tuple(getattr(ds, "ImageType", [])))
            except Exception:
                pass

        if len(zs) >= 2:
            zs_sorted = sorted(zs)
            spacings = np.diff(zs_sorted)
            result["z_stdev_mm"] = float(np.std(spacings))
            result["z_min_mm"] = float(spacings.min())
            result["z_max_mm"] = float(spacings.max())
            result["z_median_mm"] = float(np.median(spacings))
            result["z_spacing_uniform"] = result["z_stdev_mm"] <= 0.01
            result["no_duplicate_z"] = len(zs) == len(set(zs))
            if thicknesses:
                tag_thick = float(np.median(thicknesses))
                result["slice_thickness_tag_mm"] = tag_thick
                result["slice_thickness_matches_z_gap"] = abs(tag_thick - result["z_median_mm"]) <= 0.5
            else:
                result["slice_thickness_matches_z_gap"] = True
        else:
            result["z_spacing_uniform"] = True
            result["no_duplicate_z"] = True
            result["slice_thickness_matches_z_gap"] = True

        result["acquisition_numbers"] = sorted(set(acqs))
        result["single_acquisition"] = len(set(acqs)) <= 1
        result["consistent_orientation"] = len(set(iops)) <= 1 if iops else True
        result["no_localizer"] = not any("LOCALIZER" in it for it in image_types)
    else:
        result["z_spacing_uniform"] = True
        result["no_duplicate_z"] = True
        result["slice_thickness_matches_z_gap"] = True
        result["single_acquisition"] = True
        result["consistent_orientation"] = True
        result["no_localizer"] = True

    # --- Annotation checks (RTSTRUCT) ---
    rtstructs = by_modality.get("RTSTRUCT", [])
    result["n_rtstruct"] = len(rtstructs)
    result["single_rtstruct"] = len(rtstructs) <= 1

    # Annotation anchoring: do all RTSTRUCTs have ContourImageSequence on every contour?
    if rtstructs:
        anchor_ok = True
        for f, _ in rtstructs:
            try:
                ds_full = pydicom.dcmread(str(f))
            except Exception:
                anchor_ok = False
                break
            for roi in getattr(ds_full, "ROIContourSequence", []):
                for ctr in getattr(roi, "ContourSequence", []):
                    cis = getattr(ctr, "ContourImageSequence", None)
                    if not cis:
                        anchor_ok = False
                        break
                if not anchor_ok:
                    break
            if not anchor_ok:
                break
        result["annotation_anchored"] = anchor_ok
    else:
        # If no annotations, this check is N/A — treat as green
        result["annotation_anchored"] = True

    # FrameOfReferenceUID match between RTSTRUCT and image
    if rtstructs and ct_headers:
        ct_for_uids = {getattr(ds, "FrameOfReferenceUID", None) for _, ds in ct_headers}
        ct_for_uids.discard(None)
        rt_for_uids = set()
        for f, _ in rtstructs:
            try:
                ds_full = pydicom.dcmread(str(f))
                for r in getattr(ds_full, "ReferencedFrameOfReferenceSequence", []):
                    rt_for_uids.add(getattr(r, "FrameOfReferenceUID", None))
            except Exception:
                pass
        rt_for_uids.discard(None)
        result["rtstruct_for_uid_match"] = bool(ct_for_uids & rt_for_uids) if rt_for_uids else True
    else:
        result["rtstruct_for_uid_match"] = True

    # --- Verdict ---
    flags = [c for c in CHECKS if not result.get(c, True)]
    result["dirty"] = bool(flags)
    result["red_flags"] = flags
    return result


def find_series_dirs(root):
    """Return directory paths containing at least one DICOM-like file.

    A series dir is any directory that directly contains *.dcm files.
    """
    root = Path(root)
    if any(root.glob("*.dcm")) or any(root.glob("*.DCM")):
        return [root]
    return sorted({p.parent for p in root.rglob("*.dcm")} | {p.parent for p in root.rglob("*.DCM")})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--series", help="Path to a single series directory")
    g.add_argument("--root", help="Path to a dataset root; every subdir with *.dcm is audited")
    p.add_argument("--csv", help="Optional CSV report path")
    p.add_argument("--quiet", action="store_true", help="Suppress per-series stdout (exit code only)")
    args = p.parse_args()

    if args.series:
        series_dirs = [Path(args.series)]
    else:
        series_dirs = find_series_dirs(args.root)
        if not series_dirs:
            print(f"ERROR: no *.dcm files under {args.root}", file=sys.stderr)
            sys.exit(2)

    results = [audit_series(d) for d in series_dirs]
    n_dirty = sum(1 for r in results if r.get("dirty"))

    if not args.quiet:
        for r in results:
            verdict = "DIRTY" if r.get("dirty") else "clean"
            flags = ",".join(r.get("red_flags", []))
            err = r.get("error", "")
            extra = f"  flags={flags}" if flags else ""
            extra += f"  error={err}" if err else ""
            print(f"[{verdict}] {r['series']}{extra}")

        print()
        print(f"Audited {len(results)} series; {n_dirty} dirty.")

    if args.csv:
        cols = ["series", "n_files", "dirty", "red_flags"] + CHECKS + [
            "z_stdev_mm", "z_min_mm", "z_median_mm", "z_max_mm",
            "slice_thickness_tag_mm", "acquisition_numbers", "modalities", "n_rtstruct", "error",
        ]
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in results:
                row = dict(r)
                row["red_flags"] = ",".join(row.get("red_flags", []))
                row["acquisition_numbers"] = ",".join(str(x) for x in row.get("acquisition_numbers", []))
                row["modalities"] = ",".join(row.get("modalities", []))
                w.writerow(row)
        if not args.quiet:
            print(f"Wrote CSV report: {args.csv}")

    sys.exit(1 if n_dirty else 0)


if __name__ == "__main__":
    main()
