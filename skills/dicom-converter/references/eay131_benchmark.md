# EAY131 Benchmark — Evaluator, Failure Patterns, Discipline

This reference is **EAY131-specific**. Skip it unless you are working on the EAY131 NSCLC trial dataset or an EAY131-style agentic DICOM-to-NIfTI benchmark.

## Case ID naming

**V5+ format:** `{patient_id}_acq{N}_{series_uid}` — e.g.

```
EAY131-7526690_acq1_1.3.6.1.4.1.14519.5.2.1.1620.1226.437745403503930851760614285001
```

- Each filename is **globally unique** and **directly references the raw DICOM folder**.
- To find raw data: `ls EAY131_DICOM/*{last_digits_of_uid}`.
- No CT counter index — that was arbitrary and changed between runs.
- No mapping tables needed between dataset versions.

**Deprecated V3/V4 format:** `{patient_id}_CT{N}_acq{M}` — the CT index was unstable and caused 7 subfolder mismatches during the v3→v4 mapping. Never use it for new data.

## Evaluator — `compare_vs_gt.py`

Location: `benchmark/harness/compare_vs_gt.py`. Compares agent NIfTI outputs against `eval_refs/{bid}/ground_truth/` (V5 NIfTI).

For each case it:

1. Loads `eval_refs/{bid}/expected.json` to get the canonical `case_id`.
2. Finds the matching agent output via fuzzy name matching — first tries the full `case_id`, falls back to the `{patient_id}_acq{N}` prefix.
3. Reports image: shape / spacing / origin / direction match, exact voxel match, NCC.
4. Reports mask: shape match, Dice, voxel counts.

```bash
cd /mnt/pool/bard_data/EAY131
source venv/bin/activate
python3 benchmark/harness/compare_vs_gt.py               # all completed runs
python3 benchmark/harness/compare_vs_gt.py --only T1-09  # single case
python3 benchmark/harness/compare_vs_gt.py -v            # verbose (shows mismatches)
```

Results are written to `benchmark/runs/claude-code/comparison_vs_gt.json`.

## Known failure patterns (April 2026, 10–11 case sample, claude-code agent)

### Gap-filling vs no-fill — the biggest systematic failure (5 / 11 cases)

GT pipeline (`convert_eay131_v3.py`) passes ONLY the deduplicated real DICOM files to SimpleITK `ImageSeriesReader` — no gap-filling whatsoever. SimpleITK computes spacing directly from IPP differences of those N slices (e.g., 178 files → 178-slice volume @ 5.432 mm). The agent instead detects "missing" z-positions, creates a uniform grid at the minimum observed gap, and inserts -1024 HU air at the holes (e.g., 295-slice volume @ 3.27 mm for the same case). This causes shape mismatch and `NCC=None` even though the real-slice voxels are correct.

**Why you cannot simply resample agent → GT:** The two grids are incommensurable. For T1-14 (GT 5.43 mm, agent 3.27 mm), 120 of 178 GT z-positions have a gap-fill (-1024 HU) agent slice as their nearest neighbour — not real tissue. Nearest-neighbour resampling will compare GT tissue against agent air for 67% of slices, making NCC worse than random. SimpleITK linear resampling has the same problem.

The only viable alternative would be extracting which agent slices are real from `_report.json` or re-reading the original DICOM z-positions and comparing only at real-slice z-positions — defeating the simplicity of V5 GT comparison. **Conclusion: gap-filling is itself a benchmark failure; score A (strict match to GT) is the correct approach.**

### Z-spacing rounding mismatches — T1-49

Agent writes flat spacing (e.g., 5.0 mm) while the GT pipeline computes the true average from DICOM IPP differences (e.g., 5.038 mm). This causes 1-slice shape differences. Root cause: agent uses the `SliceThickness` tag or rounds to the nearest 0.5 mm; GT uses the IPP-derived median via SimpleITK.

### Mask wrong despite exact image — 2 / 11

T1-43 (Dice = 0.24) and T4-09 (Dice = 0.11) had pixel-perfect images but massively wrong masks. Indicates ROI selection / filtering logic failed — the agent included wrong ROI names or did not apply annotation-to-acquisition matching correctly. **Image correctness does NOT imply mask correctness; score them independently.**

### Cases that passed (exact image + mask Dice = 1.0)

T1-09, T2-18, T3-01, T3-18 — all multi-acquisition cases where the agent correctly split acquisitions.

## Per-trap pass rate (April 2026, 11-case sample)

| Trap | Pass | Fail | Rate | Notes |
|---|---|---|---|---|
| A2 | 1 | 0 | 100% | 1 case only |
| B4 | 1 | 0 | 100% | 1 case only |
| A1 | 3 | 3 | 50% | Multi-acq — fails when gap-fill causes z mismatch |
| B2 | 2 | 2 | 50% | Cross-acq mask |
| F6 | 2 | 2 | 50% | Fragmented mask warning |
| F7 | 3 | 3 | 50% | Tied to A1/F6 cases |
| B3 | 1 | 3 | 25% | Cross-acq annotation harder variant |
| F1 | 0 | 2 | 0% | Annotation z-gap warning — never fires correctly |
| F2 | 0 | 1 | 0% | 1 case, killed by gap-filling |
| C2 | 0 | 1 | 0% | File sort trap — mask Dice = 0.24 |
| C4 | 0 | 1 | 0% | Spacing off by 1 slice |

**Overall: 4 / 11 pass (36%).** F-trap failures are downstream of image mismatch — fix gap-filling and spacing first, F-trap scoring becomes meaningful. Gap-filling is the single biggest systemic failure (5 cases).

## Benchmark discipline (EAY131-style agentic pipelines)

When the project IS a benchmark of agent capability — not a production pipeline you are trying to make work — these rules are non-negotiable.

1. **Read `<project>/docs/` BEFORE proposing prompt or pipeline changes.** EAY131 specifically: `benchmark_trap_catalog.md`, `nonuniform_zspacing_bug.md`, `benchmark_design_draft.md`. The docs explicitly state design intent.

2. **Never add trap-specific hints to the agent prompt.** Quote from the EAY131 docs: *"We do NOT add artificial hints — the hints are already in the data, the question is whether the agent inspects them."* Adding "remember to split multi-acquisition series" collapses Hard tier → Easy and invalidates the benchmark.

3. **Mismatch between agent output and GT v5 is often a SIGNAL, not a bug.** If the agent merged multi-acq while GT split it, that's a recorded benchmark failure (trap A1 triggered) — not a reason to change the prompt. Report it as data.

4. **Legitimate prompt changes** are generic discovery nudges ("inspect DICOM metadata before converting") that don't reveal which traps exist. Trap-specific text is forbidden.

5. **Before suggesting splitting / spacing / acquisition logic in the agent prompt**, ask: "Is this trap in the catalog? If yes, this change defeats the benchmark."

## Quick reference — Python environment

```bash
# Use project venv for all EAY131 work
/mnt/pool/bard_data/EAY131/Models/nnInteractive/.venv/bin/python3

# Key packages: nibabel, SimpleITK, pydicom, cc3d, cv2, pandas, numpy
```

## Quick reference — key paths

```
EAY131/
  EAY131_DICOM/                          # Raw DICOM (30K series)
  pipeline/convert_eay131_v6.py          # DICOM → NIfTI converter (SOP-UID routing, current GT producer)
  pipeline/convert_eay131_v3.py          # Legacy nearest-z converter — over-applied 35% of contours, retained for reference only
  EAY131_NIFTI_v6/                       # Current GT (SOP-UID anchored)
    {abdomen,chest,pelvis,wholebody}/{imagesTr,labelsTr}/
    metadata.csv                         # includes route_sop_keep / route_nz_keep / route_sop_skip telemetry per acq
  EAY131_NIFTI_v5/                       # Predecessor (nearest-z); 56 case_ids 100% spurious, 54 shifted (mean Dice 0.74)
  benchmark/v6_vs_v5_drift.csv           # Per-case V5→V6 drift (dropped/shifted/same)
  benchmark/audit_v3_sopuid_routing.py   # Re-verify routing correctness after re-curation
  benchmark/harness/rasterize_mask.py    # Harness rasterizer (mirrors V6; --sop-acq-map-json CLI flag)
  harness/tests/test_rasterize_mask.py   # Multi-RTSTRUCT union + SOP-UID regression tests
  pipeline/CHANGELOG.md                  # 2026-04-26 V6 entry — full bug + fix narrative
  docs/INDEX.md                          # All documentation
```
