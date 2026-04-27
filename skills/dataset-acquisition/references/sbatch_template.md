# sbatch Template for Dataset Downloads

Use this template when generating an sbatch script for a download job. Fill in
the `<PLACEHOLDERS>` from the user's request.

## Template

```bash
#!/bin/bash
#SBATCH --account=<ACCOUNT>
#SBATCH --job-name=<JOB_NAME>
#SBATCH --time=<WALL_TIME>
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err

set -euo pipefail

# Load modules (adjust if the user has different conventions)
module load python/3.11 StdEnv/2023

# Activate venv with the needed CLI tools installed
source <VENV_PATH>/bin/activate

# Destination
DEST=<DEST_PATH>
mkdir -p "$DEST"

# <DOWNLOAD COMMAND HERE>
# e.g. gdc-client download -m /path/to/manifest.txt -d "$DEST"
# e.g. kaggle competitions download -c <slug> -p "$DEST"
# e.g. python /path/to/hf_download.py --repo-id ... --revision ... --local-dir "$DEST"
# e.g. gdown --folder <url> -O "$DEST"

# Post-download sanity check
FILE_COUNT=$(find "$DEST" -type f | wc -l)
echo "Downloaded $FILE_COUNT files to $DEST"

if [ "$FILE_COUNT" -eq 0 ]; then
    echo "ERROR: no files downloaded" >&2
    exit 1
fi
```

## Placeholder guidance

- **ACCOUNT** — the SLURM account string. Use only if the user confirms it or
  it is already in their memory context. Common at McGill/Compute Canada:
  `def-<PI>-<lab>`. If unknown, ask before generating.
- **WALL_TIME** — rough estimate based on source and size:
  - TCGA cohort, ~100 GB: `12:00:00`
  - TCGA cohort, <20 GB: `4:00:00`
  - Kaggle competition: `2:00:00`
  - HF dataset: depends on size; `4:00:00` is usually safe.
  - Always overestimate slightly — a too-short wall time wastes a queue cycle.
- **JOB_NAME** — short and identifiable, e.g. `cesc-download`, `brats-hf-pull`.
- **DEST_PATH** — if the user mentions `$SCRATCH` or `$SLURM_TMPDIR`, use
  exactly that. Prefer `$SCRATCH` for datasets that need to persist past the
  job (`$SLURM_TMPDIR` is wiped on job exit).
- **VENV_PATH** — ask the user if it is not obvious from context. Common
  patterns: `~/venvs/<project>`, `$SCRATCH/venvs/<project>`.

## When to use sbatch (recap)

Use sbatch if **any** of these apply:
- Total download is greater than ~5 GB.
- Expected wall time is greater than ~30 minutes.
- The user mentions `$SCRATCH`, `$SLURM_TMPDIR`, a SLURM account, or a cluster.
- The user explicitly asks for an sbatch script.

Otherwise, run the download command directly.

## Notes and gotchas

- **No GPU for downloads.** Waste of allocation. Do not include `--gres=gpu:*`.
- **Do not run `gdc-client` inside `$SLURM_TMPDIR`** — it gets wiped at job
  end. Use `$SCRATCH` for downloads that must persist.
- **Resume behaviour:** `gdc-client`, `kaggle`, and `huggingface_hub` resume
  to varying degrees. `gdown` mostly does not. If you re-run after a job
  killed by wall-time, expect partial results — verify file count.
- **Very large downloads (>500 GB)** are better split into manifest chunks +
  array jobs. That's beyond this template; ask the user before designing it.
- **Output / error files** go to the job's working directory by default. If
  the user wants them somewhere specific, set `--output` / `--error` to
  absolute paths.
