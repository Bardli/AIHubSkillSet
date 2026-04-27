#!/usr/bin/env python3
"""Generate a GDC manifest for a TCGA cohort using the GDC REST API.

Adapted from https://github.com/ryanwangk/medimg_skills (MIT).

Example:
    python gdc_manifest.py --project TCGA-CESC --sample-type "Primary Tumor" \\
        --data-format SVS --preservation FFPE -o cesc_manifest.txt

The manifest can then be used with: gdc-client download -m <manifest>
"""
import argparse
import json
import sys
import urllib.request
import urllib.parse


GDC_FILES_ENDPOINT = "https://api.gdc.cancer.gov/files"


def build_filters(project, sample_type, data_format, data_category, preservation, access):
    """Build the GDC filter payload."""
    content = [
        {"op": "in", "content": {"field": "cases.project.project_id", "value": [project]}},
        {"op": "in", "content": {"field": "access", "value": [access]}},
    ]
    if sample_type:
        content.append({"op": "in", "content": {"field": "cases.samples.sample_type", "value": [sample_type]}})
    if data_format:
        content.append({"op": "in", "content": {"field": "data_format", "value": [data_format]}})
    if data_category:
        content.append({"op": "in", "content": {"field": "data_category", "value": [data_category]}})
    if preservation:
        content.append({"op": "in", "content": {"field": "cases.samples.preservation_method", "value": [preservation]}})
    return {"op": "and", "content": content}


def fetch_manifest(filters, size=10000):
    params = {
        "filters": json.dumps(filters),
        "return_type": "manifest",
        "size": str(size),
    }
    url = f"{GDC_FILES_ENDPOINT}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True, help="GDC project id, e.g. TCGA-CESC")
    p.add_argument("--sample-type", help='e.g. "Primary Tumor", "Solid Tissue Normal"')
    p.add_argument("--data-format", help="e.g. SVS, BAM, VCF, TXT")
    p.add_argument("--data-category", help='e.g. "Slide Image", "Transcriptome Profiling"')
    p.add_argument("--preservation", help="e.g. FFPE, Frozen")
    p.add_argument("--access", default="open", choices=["open", "controlled"])
    p.add_argument("--size", type=int, default=10000, help="Max files to return")
    p.add_argument("-o", "--output", required=True, help="Output manifest path")
    args = p.parse_args()

    filters = build_filters(
        args.project, args.sample_type, args.data_format,
        args.data_category, args.preservation, args.access,
    )
    manifest = fetch_manifest(filters, size=args.size)

    lines = manifest.strip().splitlines()
    if len(lines) < 2:
        print("ERROR: manifest returned 0 files. Check your filters.", file=sys.stderr)
        print(f"Filters used: {json.dumps(filters, indent=2)}", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "w") as f:
        f.write(manifest)

    print(f"Wrote {len(lines) - 1} files to {args.output}")


if __name__ == "__main__":
    main()
