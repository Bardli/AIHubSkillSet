# DICOM Converter Skill for Claude Code

A [Claude Code](https://claude.com/claude-code) skill that converts DICOM
series to NIfTI, decodes RTSTRUCT and SEG annotations to label masks, audits
dataset cleanliness header-only, and routes per-contour or per-frame masks
to the correct slice/acquisition via SOP-UID anchoring.

The skill is structured around two non-negotiable rules:

1. **Audit before you convert.** A 30-second header-only audit decides whether the simple path is safe.
2. **Route annotations by SOP-UID, not by z-coordinate geometry.** This single architectural choice eliminates a whole class of bugs that look unrelated.

## Sibling skills (out of scope here)

This skill is **only** about DICOM → NIfTI and annotation decoding. Two
related concerns have their own skills in this set:

- **Acquiring DICOM data from public sources** (TCGA/GDC, Kaggle, HuggingFace,
  Google Drive) — use the sibling [`dataset-acquisition`](../dataset-acquisition/) skill.
- **nnUNet v2 dataset formatting** (`imagesTr/labelsTr/dataset.json`) on the
  resulting NIfTI files — use the sibling [`nnunet-converter`](../nnunet-converter/) skill.

If you need download → DICOM-convert → nnUNet-format end-to-end, chain all three.

## Installation

```bash
mkdir -p .claude/skills
cp -r dicom-converter .claude/skills/dicom-converter
```

Or clone the parent [AIHubSkillSet](https://github.com/Bardli/AIHubSkillSet) repo and copy the skill out:

```bash
git clone https://github.com/Bardli/AIHubSkillSet.git
cp -r AIHubSkillSet/skills/dicom-converter .claude/skills/dicom-converter
```

## Usage

Once installed, ask Claude Code about a DICOM dataset:

```
> audit this DICOM dataset before I convert it
> convert these DICOMs to NIfTI and turn the RTSTRUCT into a label mask
> debug why my labels are misaligned with the image after conversion
> handle this multi-acquisition study with overlapping z-coordinates
```

The skill runs the header-only auditor first to decide between the simple
single-pass converter and the metadata-first pipeline (per-acquisition split,
SOP-UID routing). Detailed guidance is loaded only as the data demands.

## Structure

The skill uses **progressive disclosure**: `SKILL.md` is a compact entry
point, and per-topic detail lives in `references/*.md` files that are loaded
on demand based on what the input data requires. Mandatory pre-reads are
flagged with **MUST read**.

```
dicom-converter/
├── SKILL.md                              # Compact entry point + workflow + pointer table
├── references/
│   ├── audit_checklist.md                # 10-check cleanliness audit (MUST read)
│   ├── sop_uid_routing.md                # SOP-UID-anchored mask routing
│   ├── multi_rtstruct.md                 # OR-union of multiple RTSTRUCTs
│   ├── seg_decoding.md                   # DICOM SEG per-frame routing
│   ├── image_stack_traps.md              # multi-acquisition, z-overlap, spacing
│   ├── debugging_misalignment.md         # recipes for label/image mismatch
│   ├── downstream_stages.md              # NIfTI → NPZ (optional) and inference
│   ├── visualization_qc.md               # overlay QC videos
│   └── eay131_benchmark.md               # worked example on a real dataset
├── scripts/
│   ├── audit_dicom_dataset.py            # 10-check header-only auditor
│   ├── build_sop_to_acq.py               # SOP-UID → acquisition map writer
│   ├── parse_rtstruct_union.py           # multi-RTSTRUCT OR-union parser
│   └── make_overlay_qc_videos.py         # post-conversion QC video generator
└── README.md
```

## Requirements

The generated commands use Python libraries the user must install:

- `pydicom` for DICOM parsing.
- `SimpleITK` for `ImageSeriesReader` and NIfTI I/O.
- `numpy` for mask construction.
- `nibabel` (optional) for some auditor outputs.

## License

MIT. See top-level [AIHubSkillSet](https://github.com/Bardli/AIHubSkillSet)
for licensing of bundled scripts.
