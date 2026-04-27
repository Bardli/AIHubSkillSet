# HuggingFace

Use `scripts/hf_download.py` — it wraps `huggingface_hub.snapshot_download`
and **enforces revision pinning**.

## Why pin the revision

HuggingFace repos are mutable. The `main` branch can change under you between
runs. Pinning to a commit SHA gives a truly reproducible dataset. If the user
does not provide a revision, the script resolves the current HEAD SHA and
prints it — they should pin that next time.

## Prerequisites

- `huggingface_hub` installed (`pip install huggingface_hub`). If not, install it.
- For **gated** repos (many medical datasets — MIMIC derivatives, some
  radiology collections, etc.) the user must:
  1. Open the dataset's HF page in a browser and accept the terms.
  2. Run `huggingface-cli login` with a token that has `read` access.

  If those aren't done, `snapshot_download` raises HTTP 401 / 403. Relay the
  error to the user; do not try to work around it.

## Command

```bash
python scripts/hf_download.py \
    --repo-id some-org/some-dataset \
    --repo-type dataset \
    --revision abc123def \
    --local-dir ./data
```

Flags:
- `--repo-id` — required. Format `<owner>/<name>`.
- `--repo-type` — `dataset` (default), `model`, or `space`.
- `--revision` — commit SHA, tag, or branch. **Always provide for reproducibility.**
  If omitted, the script prints the current HEAD SHA and uses it.
- `--local-dir` — required. Destination directory.
- `--allow-patterns` — optional glob patterns to limit the download. For large
  repos, e.g. `--allow-patterns "*.nii.gz" "metadata.csv"` to skip imagery you
  do not need.

## Recording the pinned revision

After the download, record the revision SHA somewhere durable:
- In a per-dataset `_manifest.json` (use the `nnunet-converter` skill's
  `write_manifest.py` if formatting for nnUNet).
- Or in your project's data README / changelog.

A download without a recorded revision is **not** reproducible.

## Common pitfalls

- Re-running `--revision main` and getting different files because the repo
  changed: pin to a SHA.
- Downloading a 200 GB repo in full because `--allow-patterns` was forgotten.
- 401/403 on a gated repo: the user has not accepted terms or has not run
  `huggingface-cli login`.
- Downloading to a directory that already contains a partial mirror — the
  `huggingface_hub` resume logic is generally safe, but verify file count and
  total size after.
