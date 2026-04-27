#!/usr/bin/env python3
"""Download a HuggingFace dataset or model repo with a pinned revision.

Adapted from https://github.com/ryanwangk/medimg_skills (MIT).

Pinning to a specific commit SHA (rather than `main`) is essential for
reproducibility — `main` moves, commits don't.

Example:
    python hf_download.py --repo-id some-org/some-dataset \\
        --repo-type dataset --revision abc123def --local-dir ./data

If --revision is omitted, the script resolves the current HEAD SHA and
prints it, so the user can pin it for next time.
"""
import argparse
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo-id", required=True)
    p.add_argument("--repo-type", default="dataset", choices=["dataset", "model", "space"])
    p.add_argument("--revision", help="Commit SHA, tag, or branch. If omitted, uses current HEAD and prints it.")
    p.add_argument("--local-dir", required=True)
    p.add_argument("--allow-patterns", nargs="+", help="Glob patterns to include")
    args = p.parse_args()

    try:
        from huggingface_hub import snapshot_download, HfApi
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub", file=sys.stderr)
        sys.exit(1)

    revision = args.revision
    if not revision:
        api = HfApi()
        info = api.repo_info(repo_id=args.repo_id, repo_type=args.repo_type)
        revision = info.sha
        print(f"No revision given. Resolved HEAD to: {revision}")
        print(f"For reproducibility, pin this next time: --revision {revision}")

    path = snapshot_download(
        repo_id=args.repo_id,
        repo_type=args.repo_type,
        revision=revision,
        local_dir=args.local_dir,
        allow_patterns=args.allow_patterns,
    )
    print(f"Downloaded to: {path}")
    print(f"Revision: {revision}")


if __name__ == "__main__":
    main()
