# AIHubSkillSet

A bundle of three [Claude Code](https://claude.com/claude-code) skills for
medical-imaging dataset work. Each skill is independent — install only the
ones you need — but they are designed to compose: typically you **acquire**
data, then **convert** DICOM to NIfTI, then **format** for nnUNet training.

## The three skills

| Skill | Purpose | Triggers on |
|---|---|---|
| [`dataset-acquisition`](./dataset-acquisition/) | Download from TCGA/GDC, Kaggle, HuggingFace, Google Drive; generate SLURM sbatch scripts | "grab the CESC slides", "pull this Kaggle competition", "download from HF and pin the revision", "sbatch script for this download" |
| [`dicom-converter`](./dicom-converter/) | DICOM series → NIfTI; RTSTRUCT/SEG handling; SOP-UID anchored routing for multi-acquisition data; debug recipes for label misalignment | "convert these DICOMs to NIfTI", "handle this RTSTRUCT", "debug this label/image mismatch", "audit this DICOM dataset" |
| [`nnunet-converter`](./nnunet-converter/) | Format imaging datasets into nnUNet v2 layout (`imagesTr`/`labelsTr`/`dataset.json`/`splits_final.json`); handles 2D PNG, 3D NIfTI/MHA/NRRD, 3D TIFF, multi-modal, classification labels, ignore label, region-based | "make this nnUNet-ready", "prepare for nnUNet training", "generate dataset.json" |

## Typical pipeline

```
        ┌──────────────────────┐
        │ dataset-acquisition  │   download from TCGA/GDC, Kaggle, HF, gdrive
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ dicom-converter      │   DICOM → NIfTI (only if input is DICOM)
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ nnunet-converter     │   nnUNet v2 layout + dataset.json + splits
        └──────────────────────┘
```

Skip any step that does not apply. If the source data is already NIfTI/MHA,
skip `dicom-converter`. If you do not need nnUNet, skip `nnunet-converter`.

## Installation

Skills are loaded from `.claude/skills/` in your project (or
`~/.claude/skills/` for user-level). Each skill in this repo lives in its own
top-level directory — copy the ones you want into your skills dir.

### Per-project (recommended)

```bash
mkdir -p .claude/skills
cp -r /path/to/AIHubSkillSet/nnunet-converter      .claude/skills/
cp -r /path/to/AIHubSkillSet/dicom-converter       .claude/skills/
cp -r /path/to/AIHubSkillSet/dataset-acquisition   .claude/skills/
```

### User-level (all projects)

```bash
mkdir -p ~/.claude/skills
cp -r /path/to/AIHubSkillSet/nnunet-converter      ~/.claude/skills/
cp -r /path/to/AIHubSkillSet/dicom-converter       ~/.claude/skills/
cp -r /path/to/AIHubSkillSet/dataset-acquisition   ~/.claude/skills/
```

### Direct from the repo

```bash
git clone https://github.com/Bardli/AIHubSkillSet.git
cp -r AIHubSkillSet/{nnunet-converter,dicom-converter,dataset-acquisition} ~/.claude/skills/
```

## Design notes

- **Progressive disclosure.** All three skills use a compact `SKILL.md`
  entry point that loads detailed `references/*.md` on demand, with
  mandatory **MUST read** pointers for the references the model has to
  consult before writing code or commands. This keeps the always-loaded
  context small while preserving the depth of each topic.
- **Strict scoping between skills.** Each skill stays in its lane and points
  at the others when a request crosses boundaries (e.g. `dataset-acquisition`
  refuses to do DICOM→NIfTI; it tells you to use `dicom-converter`).
- **Bundled scripts have attribution.** Where scripts are adapted from
  [ryanwangk/medimg_skills](https://github.com/ryanwangk/medimg_skills)
  (MIT), the script header records the source.

## Related repositories

- [Bardli/nnunet-converter-skill](https://github.com/Bardli/nnunet-converter-skill) — standalone repo for the `nnunet-converter` skill (mirrored here).
- [ryanwangk/medimg_skills](https://github.com/ryanwangk/medimg_skills) — upstream `medical-dataset-wrangler` skill that this set absorbed and split into focused pieces.

## License

MIT for content adapted from upstream sources noted in individual skill
attributions. Otherwise, follow each subdirectory's own README / SKILL.md
attribution as authoritative.
