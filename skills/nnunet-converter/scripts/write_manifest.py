#!/usr/bin/env python3
"""Write an OPTIONAL machine-readable provenance manifest for a dataset directory.

Records source, creation time, file count, and a deterministic checksum of
the file list (not file contents — that would be slow for WSI-scale data).

This is a **companion** to the mandatory `conversion_notes.md` entry
(SKILL.md Step 5). The `_manifest.json` is for tools / diffing; the
`conversion_notes.md` entry is for humans. Run both, not one or the other.
See `references/splits_and_provenance.md` for guidance.

Adapted from https://github.com/ryanwangk/medimg_skills (MIT).

Example:
    python write_manifest.py --dataset-dir ./Dataset234_PETCT \\
        --source-type local_dicom --source-path /home/user/raw_pet \\
        --extra '{"channels": ["CT", "PET"]}'
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def file_list_checksum(root: Path) -> str:
    """Hash the sorted list of (relative_path, size) tuples. Fast and deterministic."""
    h = hashlib.sha256()
    items = []
    for p in root.rglob("*"):
        if p.is_file() and p.name != "_manifest.json":
            items.append((str(p.relative_to(root)), p.stat().st_size))
    items.sort()
    for rel, size in items:
        h.update(f"{rel}\t{size}\n".encode())
    return f"sha256:{h.hexdigest()}"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset-dir", required=True)
    p.add_argument("--source-type", required=True, help="e.g. tcga_gdc, kaggle, huggingface, gdrive, local_dicom")
    p.add_argument("--source-path", help="URL, repo id, or local path")
    p.add_argument("--extra", help="Extra JSON to merge into the manifest")
    args = p.parse_args()

    root = Path(args.dataset_dir)
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    files = [p for p in root.rglob("*") if p.is_file() and p.name != "_manifest.json"]

    manifest = {
        "dataset_name": root.name,
        "created": datetime.now(timezone.utc).isoformat(),
        "source": {"type": args.source_type, "path": args.source_path},
        "num_files": len(files),
        "file_checksum": file_list_checksum(root),
    }
    if args.extra:
        manifest.update(json.loads(args.extra))

    out = root / "_manifest.json"
    with open(out, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {out}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
