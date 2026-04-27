---
name: dataset-acquisition
description: >
  Use when the user wants to pull a dataset from TCGA / GDC, Kaggle (competition
  or dataset), HuggingFace, or Google Drive, or asks for an sbatch script for a
  long download. Triggers on phrases like "grab the CESC slides", "download
  BraTS from huggingface", "pull RSNA pneumonia from kaggle", "GDC manifest",
  "gdown", "sbatch for this download", and on the tools gdc-client, kaggle,
  huggingface_hub, snapshot_download, gdown. Does NOT cover DICOM→NIfTI
  conversion or nnUNet formatting — hand off to the dicom-converter or
  nnunet-converter skill.
---

# Dataset Acquisition Skill

Generate the right commands (and sbatch scripts) to download medical imaging
and genomics datasets from public sources. The skill does **not** kick off
long-running downloads itself — it produces the commands and the sbatch script,
and the user submits them.

This SKILL.md is intentionally compact. Source-specific details live in
`references/*.md` and are loaded **on demand**. The pointer table at the end
tells you which reference to read for a given source. Mandatory pre-reads are
flagged with **MUST read** — they are non-negotiable.

---

## Scope

**This skill handles:**
- Generating GDC manifests + sbatch scripts for TCGA cohorts.
- Kaggle competition and dataset pulls.
- HuggingFace `snapshot_download` with revision pinning.
- `gdown` for shared Google Drive folders / files.
- sbatch templates sized to the download.

**This skill does NOT handle:**
- DICOM → NIfTI conversion. Use the **`dicom-converter`** skill.
- Formatting a dataset for nnUNet v2 training. Use the **`nnunet-converter`** skill.
- WSI tiling, stain normalization, tissue detection. Out of scope for any of these skills.
- Controlled-access TCGA data. The user manages their own GDC token; this skill defaults to `--access open`.
- Private / gated HF repos beyond running `huggingface-cli login`.

If the user asks for any of the **NOT handled** items, tell them which sibling
skill to use (or that the workflow doesn't exist) and stop.

---

## Workflow

### Step 1 — Identify the source(s)

Decide which of the four sources the user actually wants. Most requests are
single-source; some are "grab data from X then preprocess with Y" — handle the
acquisition part here and hand off to the appropriate sibling skill for the
preprocessing.

### Step 2 — Verify prerequisites BEFORE running anything

For each source, you **MUST** read the corresponding reference and confirm
its prerequisite checks pass. Do **not** try to work around missing auth — tell
the user what's missing and stop.

| Source | Mandatory pre-read |
|---|---|
| TCGA / GDC | **MUST** read `references/tcga_gdc.md` before generating any manifest or running `gdc-client`. |
| Kaggle competitions or datasets | **MUST** read `references/kaggle.md` before running `kaggle competitions download` or `kaggle datasets download`. |
| HuggingFace dataset or model | **MUST** read `references/huggingface.md` before running `snapshot_download`. |
| Google Drive (`gdown`) | **MUST** read `references/google_drive.md` before running `gdown`. |

### Step 3 — Choose between live download and sbatch

You **MUST** read `references/sbatch_template.md` before generating any sbatch
script. Use sbatch when **any** of these apply:

- Total download is greater than ~5 GB.
- Expected wall time is greater than ~30 minutes.
- The user mentions `$SCRATCH`, `$SLURM_TMPDIR`, a SLURM account, or a cluster.
- The user explicitly asks for an sbatch script.

Otherwise, run the download command directly in the user's session.

### Step 4 — Run or hand off the script

For live runs, execute the command and report the result. For sbatch jobs,
print the generated script to the user with the suggested filename and tell
them to `sbatch` it themselves — never `sbatch` it for them.

### Step 5 — Provenance (recommended)

After the data lands, recommend writing a provenance manifest:

- If the data is being prepared for nnUNet training, defer to the
  `nnunet-converter` skill's `scripts/write_manifest.py` once the dataset has
  been formatted. That writes `_manifest.json` with file-list checksum and
  source metadata.
- For a raw download that won't go through nnUNet, suggest the user record at
  minimum: source URL / repo id, download date, file count, and (for HF) the
  pinned revision SHA.

This step is **strongly recommended but not enforced** — `dataset-acquisition`
does not, by itself, produce a structured manifest. Reproducibility comes from
pinning revisions / GDC manifests at acquisition time and recording them.

---

## Quick reference: source → command

| Source | Command shape | Notes |
|---|---|---|
| TCGA / GDC | `scripts/gdc_manifest.py … -o m.txt` then `gdc-client download -m m.txt -d <dest>` | Open data only by default; controlled needs token. |
| Kaggle competition | `kaggle competitions download -c <slug> -p <dest>` | User must accept rules on kaggle.com first. |
| Kaggle dataset | `kaggle datasets download -d <owner>/<name> -p <dest> --unzip` | `--unzip` only works for datasets. |
| HuggingFace | `python scripts/hf_download.py --repo-id … --revision <SHA> --local-dir <dest>` | Always pin the revision. |
| Google Drive | `gdown <url>` or `gdown --folder <url>` | Public/shared only. No reliable resume. |

The detailed flags, common cohorts, gating notes, and rate-limit behaviours are
in the per-source references.

---

## Pointer Reference Table

| Situation | Action |
|---|---|
| Pulling a TCGA cohort, generating a GDC manifest, controlled vs open data | **MUST** read `references/tcga_gdc.md`. |
| Pulling a Kaggle competition or dataset | **MUST** read `references/kaggle.md`. |
| Pulling a HuggingFace dataset or model, gated repos, revision pinning | **MUST** read `references/huggingface.md`. |
| Pulling from Google Drive via `gdown` | **MUST** read `references/google_drive.md`. |
| Generating an sbatch script for any download | **MUST** read `references/sbatch_template.md`. |
| Preprocessing the downloaded data | Hand off to `dicom-converter` (DICOM→NIfTI) or `nnunet-converter` (nnUNet formatting). |

---

## Files in this skill

```
dataset-acquisition/
├── SKILL.md                         # This file (entry point)
├── references/
│   ├── tcga_gdc.md                  # TCGA / GDC: filters, common cohorts, controlled vs open
│   ├── kaggle.md                    # Kaggle competitions + datasets, prerequisite checks
│   ├── huggingface.md               # HF snapshot_download, revision pinning, gated repos
│   ├── google_drive.md              # gdown, public/shared limits, rate limits
│   └── sbatch_template.md           # SLURM sbatch template for downloads
├── scripts/
│   ├── gdc_manifest.py              # Generate a GDC manifest via the GDC REST API
│   └── hf_download.py               # snapshot_download with mandatory revision pinning
└── README.md
```

`gdc_manifest.py` and `hf_download.py` were adapted from
[ryanwangk/medimg_skills](https://github.com/ryanwangk/medimg_skills) under MIT.

---

## Principles

- **Fail loudly, not silently.** If a manifest returns zero files or auth is
  missing, stop and tell the user — don't paper over it.
- **The user controls long-running work.** Generate sbatch scripts for slow
  downloads; don't block a Claude turn on a four-hour transfer.
- **Pin revisions.** HuggingFace `main` moves; commit SHAs don't. The
  `hf_download.py` helper enforces this.
- **Don't manage secrets for the user.** GDC tokens, Kaggle API keys, HF
  tokens — relay errors and tell the user how to fix them. Never write or
  modify those credentials yourself.
