# AIHubSkillSet

A [Claude Code](https://claude.com/claude-code) **plugin marketplace** bundling three composable skills for medical-imaging dataset work: dataset acquisition, DICOM → NIfTI conversion, and nnUNet v2 formatting.

The three skills are independent — Claude loads each one on demand based on the task — but they are designed to compose: typically you **acquire** data, then **convert** DICOM to NIfTI, then **format** for nnUNet training.

## Install (recommended — auto-update on `/plugin update`)

```text
/plugin marketplace add Bardli/AIHubSkillSet
/plugin install ai-hub-skill-set@ai-hub-skill-set
```

Then `/plugin list` to confirm and `/plugin update ai-hub-skill-set@ai-hub-skill-set` whenever you want to pull new revisions.

## The three skills

| Skill | Purpose | Triggers on |
|---|---|---|
| [`dataset-acquisition`](./skills/dataset-acquisition/) | Download from TCGA/GDC, Kaggle, HuggingFace, Google Drive; generate SLURM sbatch scripts | "grab the CESC slides", "pull this Kaggle competition", "download from HF and pin the revision", "sbatch script for this download" |
| [`dicom-converter`](./skills/dicom-converter/) | DICOM series → NIfTI; RTSTRUCT/SEG handling; SOP-UID-anchored routing for multi-acquisition data; 10-check audit script; multi-RTSTRUCT OR-union; debug recipes for label misalignment | "convert these DICOMs to NIfTI", "handle this RTSTRUCT", "debug this label/image mismatch", "audit this DICOM dataset" |
| [`nnunet-converter`](./skills/nnunet-converter/) | Format imaging datasets into nnUNet v2 layout (`imagesTr`/`labelsTr`/`dataset.json`/`splits_final.json`); handles 2D PNG/BMP/TIFF, 3D NIfTI/MHA/NRRD, 3D TIFF, multi-modal, classification labels, ignore label, region-based | "make this nnUNet-ready", "prepare for nnUNet training", "generate dataset.json" |

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

Skip any step that does not apply. If the source data is already NIfTI/MHA, skip `dicom-converter`. If you do not need nnUNet, skip `nnunet-converter`.

## Manual install (without the marketplace)

If you prefer to vendor the skills directly into a project (no auto-update):

```bash
git clone https://github.com/Bardli/AIHubSkillSet.git
mkdir -p ~/.claude/skills            # or .claude/skills/ for project-scoped
cp -r AIHubSkillSet/skills/* ~/.claude/skills/
```

You can also copy individual skills if you only want one or two:

```bash
cp -r AIHubSkillSet/skills/nnunet-converter ~/.claude/skills/
```

## Repository layout

```
AIHubSkillSet/
├── .claude-plugin/
│   ├── marketplace.json          # marketplace declaration
│   └── plugin.json               # this repo IS the plugin (one plugin, three skills)
├── skills/
│   ├── nnunet-converter/         # progressive-disclosure skill
│   │   ├── SKILL.md
│   │   ├── references/           # 10 topical .md files
│   │   └── scripts/              # convert_template, simple-CLI, manifest writer
│   ├── dataset-acquisition/      # progressive-disclosure skill
│   │   ├── SKILL.md
│   │   ├── references/           # tcga_gdc, kaggle, huggingface, google_drive, sbatch_template
│   │   └── scripts/              # gdc_manifest.py, hf_download.py
│   └── dicom-converter/          # progressive-disclosure skill
│       ├── SKILL.md
│       ├── references/           # 9 topical .md files (audit, SOP-UID routing, multi-RTSTRUCT, etc.)
│       └── scripts/              # audit_dicom_dataset, build_sop_to_acq, parse_rtstruct_union
└── README.md
```

## Design notes

- **Progressive disclosure.** All three skills use a compact `SKILL.md` entry point that loads detailed `references/*.md` on demand, with mandatory **MUST read** pointers for the references the model has to consult before writing code or commands. This keeps the always-loaded context small while preserving the depth of each topic.
- **Strict scoping between skills.** Each skill stays in its lane and points at the others when a request crosses boundaries (e.g. `dataset-acquisition` refuses to do DICOM→NIfTI; it tells you to use `dicom-converter`).
- **Bundled scripts have attribution.** Where scripts are adapted from [ryanwangk/medimg_skills](https://github.com/ryanwangk/medimg_skills) (MIT), the script header records the source.

## Related repositories

- [Bardli/nnunet-converter-skill](https://github.com/Bardli/nnunet-converter-skill) — standalone repo for the `nnunet-converter` skill (mirrored here).
- [ryanwangk/medimg_skills](https://github.com/ryanwangk/medimg_skills) — upstream `medical-dataset-wrangler` skill that this set absorbed and split into focused pieces.
- [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) — the marketplace structure used here is modelled on this repo.

## License

MIT for content adapted from upstream sources noted in individual skill attributions. Otherwise, follow each subdirectory's own README / SKILL.md attribution as authoritative.
