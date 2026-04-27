# Dataset Acquisition Skill for Claude Code

A [Claude Code](https://claude.com/claude-code) skill that generates the
right command lines and SLURM sbatch scripts for downloading medical imaging
and genomics datasets from common public sources.

Sources covered: TCGA / GDC, Kaggle (competitions and datasets), HuggingFace
(with mandatory revision pinning), and Google Drive (`gdown`).

## Out of scope (use sibling skills)

This skill is **only** about acquisition. Two related preprocessing concerns
have their own skills:

- **DICOM → NIfTI conversion** — use the `dicom-converter` skill.
- **nnUNet v2 dataset formatting (`imagesTr/labelsTr/dataset.json`)** — use
  the `nnunet-converter` skill (<https://github.com/Bardli/nnunet-converter-skill>).

If a user asks for download + nnUNet formatting in one go, this skill produces
the download artifacts; hand off to `nnunet-converter` for the formatting.

## Installation

```bash
mkdir -p .claude/skills
cp -r dataset-acquisition .claude/skills/dataset-acquisition
```

Or clone directly into the skills directory:

```bash
git clone <repo-url> .claude/skills/dataset-acquisition
```

## Usage

Once installed, ask Claude Code to download a dataset:

```
> generate a GDC manifest for TCGA-CESC FFPE diagnostic slides
> pull the BraTS 2024 dataset from huggingface to $SCRATCH/datasets/brats
> write me an sbatch script to download the RSNA pneumonia competition
> grab a public Google Drive folder of model weights to ./weights
```

The skill will check prerequisites (CLI installed, auth files present, rules
accepted) and either run the command directly (small pulls) or generate an
sbatch script (large pulls).

## Structure

The skill uses **progressive disclosure**: `SKILL.md` is a compact entry
point, and per-source detail lives in `references/*.md` files that are loaded
on demand based on which source the user is asking about.

```
dataset-acquisition/
├── SKILL.md                         # Compact entry point + workflow + pointer table
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

## Requirements

The generated commands invoke external CLIs the user must install:

- `gdc-client` for TCGA / GDC.
- `kaggle` for Kaggle (`pip install kaggle`).
- `huggingface_hub` for HF (`pip install huggingface_hub`).
- `gdown` for Google Drive (`pip install gdown`).

This skill does **not** install or auto-configure any of those.

## Attribution

`scripts/gdc_manifest.py` and `scripts/hf_download.py` are adapted from
[ryanwangk/medimg_skills](https://github.com/ryanwangk/medimg_skills)
(`medical-dataset-wrangler`) under MIT. The reference structure and several
prerequisite-check lessons also come from that skill.

## License

MIT
