---
name: dicom-converter
description: Use when converting DICOM series to NIfTI, handling RTSTRUCT/SEG annotations, auditing a DICOM dataset's health (clean vs dirty), routing per-contour or per-frame masks to the correct slice/acquisition, or debugging DICOM→NIfTI label misalignment. Triggers on keywords like DICOM, NIfTI, nii.gz, RTSTRUCT, SEG, SimpleITK, ImageSeriesReader, pydicom, ImagePositionPatient, AcquisitionNumber, SOPInstanceUID, ContourImageSequence, DerivationImageSequence, multi-acquisition, z-spacing, sop_to_acq.
---

# DICOM Converter

## Overview

How to take a directory of DICOM files and produce correct NIfTI images and label masks. Covers the audit step that decides whether the simple `sitk.ImageSeriesReader` path is safe vs. when you must use the metadata-first (V6) pipeline, the SOP-UID anchoring pattern that eliminates a class of "geometry-based" routing bugs, and the debugging recipes for label misalignment. Downstream stages (NPZ packing, inference, visualization) are kept as appendices for context — the core is DICOM → NIfTI.

## Pipeline Stages

```
DICOM (raw)
  │  Stage 1: DICOM → NIfTI (HARD — metadata traps)
  ▼
NIfTI (image + label pairs)
  │  Stage 2: NIfTI → NPZ (EASY — but windowing matters)
  ▼
NPZ (uint8 CT + instance labels + RECIST prompts)
  │  Stage 3: Inference (model-specific)
  ▼
Predictions → Evaluation (DSC, visualization)
```

## Stage 1: DICOM → NIfTI — Critical Traps

### Audit before you convert — clean vs dirty routing

**Don't assume clinical data is clean.** A 30-second header-only scan tells you whether the simple `sitk.ImageSeriesReader` path is safe or whether you must route through the metadata-first V6 pipeline. Cheap to run (`pydicom.dcmread(stop_before_pixels=True)`), expensive to skip.

Per-series checks — any single red flag → dirty:

| # | Check | Trigger condition | Why it matters |
|---|---|---|---|
| 1 | Z-spacing uniformity | `np.std(np.diff(sorted(z))) > 0.01 mm` | SimpleITK forces a uniform grid; non-uniform → wrong z-indices in any geometric lookup. |
| 2 | Multi-acquisition under one SeriesUID | `len(set(AcquisitionNumber)) > 1` | `ImageSeriesReader` merges acquisitions into one volume; HU jumps + cross-phase blending. |
| 3 | Duplicate z-positions | `len(z) != len(set(z))` | Same physical z has multiple slices (overlapping recon or multi-acq); SimpleITK spacing breaks. |
| 4 | Orientation consistency | `ImageOrientationPatient` deviates from `[1,0,0,0,1,0]` or varies across slices | Coronal/sagittal/tilted → z ≠ IPP[2]; downstream code assuming axial is wrong. |
| 5 | Annotation anchoring | RTSTRUCT contour missing `ContourImageSequence`, or SEG frame missing `DerivationImageSequence.SourceImageSequence` | No SOP UID → forced into fragile nearest-z fallback. EAY131 V6 fallback rate is ~0.8% of contours, 0% of SEG frames; higher = data is dirty. |
| 6 | Multi-RTSTRUCT in annotation dir | `>1` `*.dcm` with `Modality=='RTSTRUCT'` | Reading only `dcm_files[0]` drops N-1 ROIs (10× undercount measured on EAY131-8365856 acq2). |
| 7 | Modality mixing in input dir | More than one `Modality` in same folder | RTSTRUCT/SEG mixed with CT confuses `ImageSeriesReader`; separate before conversion. |
| 8 | `SliceThickness` vs computed z-gap | `abs(SliceThickness - median(diff(z))) > 0.5 mm` | Tag and reality disagree — never trust the `SliceThickness` tag for spacing. |
| 9 | Localizer/scout mixed in | Any file with `'LOCALIZER'` in `ImageType` | 1–3 single-frame scouts pollute the volume; must be filtered. |
| 10 | RTSTRUCT FrameOfReferenceUID linkage | RTSTRUCT `ReferencedFrameOfReferenceSequence[0].FrameOfReferenceUID` ∉ {CT FoR UIDs} | Annotation references a different study/scan than the CT in the directory. |

**Decision rule:**

```
all green  →  use the simple converter (sitk.ImageSeriesReader, single pass)
any red    →  use the metadata-first V6 pipeline (per-acq split, sop_to_acq emitted)
hard error →  fail loudly; do not silently produce a corrupted NIfTI
```

**Reference auditor:** `EAY131/pipeline/audit_dicom_dataset.py` — header-only, runs all 10 checks, exits 0/clean or 1/dirty, optional CSV + JSON reports. Use it to gate any new dataset before deciding which converter to run.

**Cleanliness reference points:**

| Dataset | Health | Converter |
|---|---|---|
| MSD, BraTS, KiTS, AMOS challenges | Clean — uniform z, axial, single-acq | Simple `sitk.ImageSeriesReader` |
| PROSTATEx-Seg-HiRes (T2 MRI) | Mostly clean — uniform spacing, single-acq SEG | `sitk.ReadImage` direct (Stage 1 §SEG path) |
| EAY131 (NSCLC trial CT) | Dirty — 84% non-uniform z, 46%+ duplicate z, frequent multi-acq, 59 interleaved series | `convert_eay131_v6.py` (metadata-first) |

### Step 0 — Read RTSTRUCT/SEG metadata BEFORE rasterizing (the highest-leverage rule)

Labeling software (RayStation, MIM, …) records *exactly which 2D image the physician was viewing* when each contour was drawn. That reference is the ground truth for slice assignment — **read it first, route by it, do not match contours to slices by z-coordinate geometry.**

- **RTSTRUCT**: per-contour `ContourImageSequence[0].ReferencedSOPInstanceUID`
- **SEG**: per-frame `PerFrameFunctionalGroupsSequence[i].DerivationImageSequence[0].SourceImageSequence[0].ReferencedSOPInstanceUID`

Build a `{SOPInstanceUID → AcquisitionNumber}` map from the CT files once, then route every contour/frame through it. This single architectural choice eliminates a whole class of "downstream" bugs that look unrelated:

| Symptom that LOOKS like its own bug | Actually a missed metadata read |
|---|---|
| "Contours outside z-range" rejected/clamped | Contour was anchored to a specific CT slice; no z-range check needed |
| Same contour leaks into two acquisitions on shared-z slices | SOP UID picks the right acquisition; geometry can't disambiguate |
| Annotators drew on a "merged" multi-acq view; SEG frames alternate | Each frame names its source CT slice — handle them one by one |
| Off-by-one slice from non-uniform z-spacing | Slice is named by UID, not derived from a z-grid |
| Mask "shifted by a couple slices" after dedup/sort changes | UID survives sort changes; z-coordinate doesn't |

**Quantified (EAY131 V3 → V6, 2026-04-26):** V3's nearest-z heuristic over-applied 851 / 2,462 RTSTRUCT contours (35%) across 7 case_ids; V6 SOP-UID routing purged 4.6M spurious GT voxels and dropped 56 fully-spurious case_ids. Only 660 / 84,539 contours (~0.8%) needed nearest-z fallback (UID truly absent). For SEG: 0 fallback.

**The pattern (`pipeline/convert_eay131_v6.py`, harness mirror in `benchmark/harness/rasterize_mask.py`):**

```python
# 1. Build SOP-UID → acquisition map from CT headers (per series, once).
sop_to_acq = {}
for f in ct_files:
    ds = pydicom.dcmread(f, stop_before_pixels=True)
    sop_to_acq[ds.SOPInstanceUID] = int(getattr(ds, "AcquisitionNumber", 1))

# 2. parse_rtstruct: capture per-contour SOP UID anchor.
for contour in roi.ContourSequence:
    cis = getattr(contour, "ContourImageSequence", None)
    sop_uid = cis[0].ReferencedSOPInstanceUID if cis else None
    contours.append({"points": ..., "sop_uid": sop_uid, ...})

# 3. Route by SOP UID first; nearest-z is fallback ONLY when UID absent/unknown.
def route_for_acq(mean_z, acq_num, z_positions, all_acq_z, sop_uid, sop_to_acq):
    if sop_uid and sop_to_acq and sop_uid in sop_to_acq:
        return "keep" if sop_to_acq[sop_uid] == acq_num else "skip"
    return belongs_to_acq_nearest_z(mean_z, acq_num, z_positions, all_acq_z)

# 4. SEG: same pattern, source UID lives in DerivationImageSequence.
def frame_source_sop_uid(per_frame_fg):
    try:
        return per_frame_fg.DerivationImageSequence[0] \
                          .SourceImageSequence[0].ReferencedSOPInstanceUID
    except (AttributeError, IndexError):
        return None
```

**Iterate ALL `*.dcm` in the annotation directory.** Many pipelines emit one RTSTRUCT file per ROI. Reading only `dcm_files[0]` silently drops N-1 ROIs — measured impact on EAY131-8365856 acq2: 13,929 voxels (single file) vs 145,642 voxels (8-file union), a 10× undercount and the root cause of P0 image_slices NCC collapse in Smoke Run 2.

```python
results = []
for f in sorted(annotation_dir.glob("*.dcm")):
    try:
        ds = pydicom.dcmread(str(f))
    except (pydicom.errors.InvalidDicomError, IsADirectoryError):
        continue
    if getattr(ds, "Modality", None) != "RTSTRUCT":
        continue
    results.extend(parse_one_rtstruct(ds))
return results if results else None
```

**Build sop_to_acq from the full per-acquisition file list, not from a z-deduped subset.** A z-dedup that prunes `sop_to_acq` re-introduces nearest-z fallback for any duplicate-z slice and silently leaks contours back into the wrong acq (EAY131 V6 dedup bug, patched 2026-04-26).

### Other traps (still real — orthogonal to Step 0):

1. **Multi-acquisition**: One series UID can contain 2-3 scan passes. Check `AcquisitionNumber` per file. Different pixel data at same z-position (up to 1900 HU difference). Step 0 handles annotation routing; you still must split *images* by AcquisitionNumber before stacking with SimpleITK.

2. **Duplicate z-positions**: 46%+ of CT series have multiple files at same z. Deduplicate before SimpleITK or spacing will be wrong. (Dedup the *image stack*; do **not** prune the SOP-UID map — see warning above.)

3. **Non-uniform z-spacing**: Common in CT (84% of EAY131 series). SimpleITK forces a uniform grid — `TransformPhysicalPointToContinuousIndex()` gives WRONG z-indices when z is non-uniform. This affects *pixel-data stacking and any geometric contour rasterization*; the SOP-UID routing in Step 0 makes it irrelevant for slice *assignment*, but you still need actual z-positions when you draw the polygon onto its anchored slice. **MRI sanity check first**: `np.std(np.diff(z_positions)) < 0.1` → SimpleITK is safe.

4. **Non-axial orientation**: 40% of series are coronal/sagittal. Check `ImageOrientationPatient` — don't assume z = IPP[2].

5. **RTSTRUCT referenced series**: Use `ReferencedSeriesInstanceUID` to pair annotations with the correct CT. Don't guess by shape.

6. **Seed points**: 2-point `CLOSED_PLANAR` ROIs. Detect by name (`"SEED POINT"` in ROI name, after stripping any leading-digit prefix) or point count. Rasterization produces empty masks; suppress them at parse time.

7. **SEG vs RTSTRUCT, simple-vs-manual**: For uniform-spacing data (most MRI), `sitk.ReadImage(seg_path)` reads DICOM SEG directly with correct geometry — no manual frame decoding needed. Drop to manual pydicom (with the Step 0 SourceImageSequence routing) only when z is non-uniform, multi-acquisition, or has duplicate z. The simple path is correct ~most of the time — try it first.

### DICOM SEG decoding — choose the right approach

**Start simple, escalate only when needed.** The traps above (non-uniform z, multi-acquisition, duplicates) are real but not universal. Check whether they apply before adding workarounds.

```
Is z-spacing uniform?
  ├── YES (most MRI, some CT) → sitk.ReadImage(seg_path) works
  │   SEG and image at same resolution? 
  │     ├── YES → map frames directly to ref image slices
  │     └── NO  → sitk.ReadImage + sitk.Resample(nearest-neighbor) to ref space
  └── NO (EAY131 CT, many clinical CT) → manual pydicom frame decoding
      Extract actual z-positions, use np.argmin nearest-neighbor lookup
      Do NOT use sitk.Resample or TransformPhysicalPointToContinuousIndex for z
```

**How to check z-spacing uniformity:**
```python
zs = sorted([float(pydicom.dcmread(f, stop_before_pixels=True).ImagePositionPatient[2]) for f in dcm_files])
spacings = np.diff(zs)
is_uniform = np.std(spacings) < 0.1  # True → SimpleITK is safe
```

**Lesson learned (PROSTATEx-Seg-HiRes, 2026-04-10):** Defaulting to manual pydicom SEG decoding (learned from EAY131 CT non-uniform z-spacing bugs) caused 38/66 failures when applied to MRI data with uniform spacing. The manual approach introduced a direction matrix transposition bug. `sitk.ReadImage()` + nearest-neighbor resample solved it cleanly. The workaround was harder than the problem.

### Debugging label misalignment

When labels look "shifted a couple slices":
```python
# Check HU at label locations — should match expected tissue
img_data = nib.load(img_path).get_fdata()
lbl_data = nib.load(lbl_path).get_fdata()
hu_at_label = img_data[lbl_data > 0].mean()
# Liver/kidney/pancreas: 40-100 HU
# Lung tumor: -50 to 50 HU  
# Air: -1000 HU (WRONG if label is here)
# Bone: +1000 HU (WRONG for soft tissue label)
```

Check z-spacing uniformity:
```python
import pydicom
zs = sorted([float(ds.ImagePositionPatient[2]) for ds in dcm_files])
spacings = np.diff(zs)
if np.std(spacings) > 1.0:
    print("NON-UNIFORM — SimpleITK grid is wrong")
```

## Stage 2: NIfTI → NPZ

### CT Windowing — per body part

| Body Part | Level (HU) | Width (HU) | Use for |
|-----------|-----------|-----------|---------|
| Abdomen   | 40        | 400       | Liver, kidney, pancreas, colon |
| Chest     | -600      | 1500      | Lung parenchyma + mediastinum |
| Pelvis    | 40        | 400       | Rectum, pelvic organs |
| Bone      | 400       | 1800      | Bone metastases |

```python
def ct_window_uint8(data, level, width):
    lo = level - width / 2
    hi = level + width / 2
    return ((np.clip(data, lo, hi) - lo) / (hi - lo) * 255).astype(np.uint8)
```

**Wrong windowing destroys contrast.** Abdomen window on lung makes lesions invisible.

### NPZ format (for MedSAM2 / EfficientMedSAM2)

```python
np.savez_compressed(path,
    imgs=ct_uint8,         # (Z,Y,X) uint8
    gts=instance_labels,   # (Z,Y,X) uint8, cc3d connectivity=26
    recist=recist_lines,   # (Z,Y,X) uint8, LD lines on key slice
    spacing=spacing,       # (3,) float64 (x,y,z) mm
    direction=direction,   # (9,) float64
    origin=origin,         # (3,) float64 (x,y,z) mm
)
```

## Stage 3: Inference

### Docker GPU Fix (ALL competition images)

ALL competition docker images hardcode `CUDA_VISIBLE_DEVICES=""`. Without fix: CPU-only, 3+ hours/case. With fix: minutes/case.

```bash
docker run --rm --gpus "device=$GPU" \
    -e CUDA_VISIBLE_DEVICES=0 \
    -v "$INPUT":/workspace/inputs:ro \
    -v "$OUTPUT":/workspace/outputs \
    $IMAGE:latest \
    /bin/bash -c "
        for f in *.py; do
            sed -i \"s/os.environ\['CUDA_VISIBLE_DEVICES'\] = ''/os.environ['CUDA_VISIBLE_DEVICES'] = '0'/\" \"\$f\"
            sed -i \"s/device='cpu'/device='cuda'/g\" \"\$f\"
        done
        python3 \$SCRIPT --imgs_path /workspace/inputs --pred_save_dir /workspace/outputs
    "
```

**Verify**: `nvidia-smi` should show >2GB mem, >50% util. If 15MB/4% → fix didn't apply.

Docker symlinks don't work — mount real directories, not symlink splits.

See: `docs/docker_gpu_fixes.md`

## Visualization Patterns

### Segmentation overlay visual QC — send to Claude Code with thinking mode

Use this when you want an AI visual quality review of segmentation predictions vs GT across N sampled cases.

**Step 1 — Generate overlay PNGs (3-panel: image | image+GT green | image+pred red):**

```python
import random, numpy as np, nibabel as nib, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

IMAGES_DIR = Path(".../imagesTr/t2")   # _0000.nii.gz files
LABELS_DIR = Path(".../labelsTr")      # GT .nii.gz
PREDS_DIR  = Path(".../predictions")   # prediction .nii.gz
OUT_DIR    = Path("/tmp/seg_overlays"); OUT_DIR.mkdir(exist_ok=True)
N_SAMPLES  = 100; SEED = 42

def window_mri(vol):
    p1, p99 = np.percentile(vol, 1), np.percentile(vol, 99)
    return np.clip((vol - p1) / (p99 - p1 + 1e-8), 0, 1)

def best_slice(gt, pred):
    combined = np.clip(gt + pred, 0, 1)
    counts = combined.sum(axis=(0, 1))
    return int(np.argmax(counts)) if counts.max() > 0 else gt.shape[2] // 2

def make_overlay(ax, img_sl, mask_sl, color, alpha=0.45):
    ax.imshow(img_sl.T, cmap='gray', origin='lower')
    if mask_sl.max() > 0:
        rgba = np.zeros((*mask_sl.T.shape, 4))
        ch = 1 if color == 'green' else 0
        rgba[..., ch] = mask_sl.T
        rgba[..., 3] = mask_sl.T * alpha
        ax.imshow(rgba, origin='lower')

# IMPORTANT: best_slice should use max(GT ∪ Pred), NOT just max(Pred)
# — otherwise GT appears empty on the displayed slice (a visualization artifact
#   that misleads the reviewer into thinking the model has no GT to compare to).
# This was flagged by Claude Code visual QC review (April 2026).
```

**Step 2 — Write a QC prompt file and launch Claude Code with thinking mode:**

```bash
cat > /tmp/qc_prompt.md << 'EOF'
# Segmentation Quality Check — <model_name>

## Images
Location: /tmp/seg_overlays/  (100 PNG files)
Each PNG: 3 panels — LEFT: image only | MIDDLE: image+GT (green) | RIGHT: image+pred (red)
Bottom text: Slice Dice, GT voxels, Pred voxels

## Task
Review ALL 100 images. Structure your report as:
1. Overall Quality Summary (good/acceptable/poor % estimate)
2. Good Cases (5-10 examples, what makes them good)
3. Failure Cases (all clear failures: case name, type, severity mild/moderate/severe)
4. Failure Mode Categories (over-seg, under-seg, false positives, boundary errors, complete failures)
5. Patterns (systematic biases, anatomy consistently missed/over-included)
6. Recommendations (production-ready? fixes? estimated volumetric DSC)

Use ultrathink — this is a critical clinical quality review.
EOF

claude --model claude-opus-4-6 --effort max \
    -p "$(cat /tmp/qc_prompt.md)" \
    --allowedTools 'Read,Bash' \
    --add-dir /tmp/seg_overlays \
    --max-turns 30 \
    2>&1 | tee /tmp/qc_output.txt
```

**Pitfalls:**
- With `--effort max` and 100 images, Claude Code stays silent for 3-5 minutes during extended thinking before outputting anything. Don't kill the process — check with `wc -c /tmp/qc_output.txt` to see if output has started.
- Slice selection MUST use `max(GT ∪ Pred)` combined mask for best_slice, not just prediction. Using max(Pred) causes the GT panel to show empty masks, making the reviewer unable to compare.
- For T2 MRI, use percentile normalization (p1/p99) not HU windowing.

**What to expect from Claude Code visual review:**
- Categorizes failures into types (over-seg, FPs, shape distortion)
- Estimates production-readiness
- Recommends immediate fixes (e.g., largest-connected-component post-processing)
- May flag visualization artifacts (e.g., empty GT panels) — take these seriously

### Per-case review video (left CT, right CT+GT overlay)

```python
PANEL = 384; HEADER_H = 40; FPS = 15; ALPHA = 0.45
# For each slice z:
#   Left panel: windowed CT (grayscale)
#   Right panel: CT + green overlay + white contours
#   Header: case_id, slice number, DSC if available
#   Color-code header by DSC: red<0.3, orange<0.5, yellow<0.7, green>=0.7
```

### Side-by-side comparison (before/after fix)

Three panels: CT | Version A | Version B. Header shows SAME (green) or DIFF (orange).

### Grid QC video (10x5 grid, 50 cases)

Scroll through z simultaneously. Flag cells with red border + DSC label for low-scoring cases.

## Dataset Selection & QC Workflow

1. **Initial selection** → generate per-case videos → manual review
2. **Mark bad cases** → exclude, pick candidates from pool
3. **Generate candidate videos** → review → approve/reject
4. **Track everything in CSVs**: `selection.csv`, `candidates.csv`, `exclude.csv`, `bad_cases.csv`
5. **No wholebody in cancer-type selections** — replace with single-subfolder candidates

### Pool priority: referenced > unreferenced > global_exclude

## Case ID Naming

**V5+ format**: `{patient_id}_acq{N}_{series_uid}` — e.g., `EAY131-7526690_acq1_1.3.6.1.4.1.14519.5.2.1.1620.1226.437745403503930851760614285001`

- Each filename is **globally unique** and **directly references** the raw DICOM folder
- To find raw data: `ls EAY131_DICOM/*{last_digits_of_uid}`
- No CT counter index — it was arbitrary and changed between runs
- No mapping tables needed between dataset versions

**Previous format (V3/V4)**: `{patient_id}_CT{N}_acq{M}` — CT index was unstable, caused 7 subfolder mismatches during v3→v4 mapping. Deprecated.

## Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Route contours/frames to acquisitions by z-coordinate geometry | Cross-acq leakage, "outside-z-range" rejections, off-by-one slices on shared-z, mask shifts under non-uniform z | Step 0: route by `ContourImageSequence` / `DerivationImageSequence` SOP UID. Nearest-z is fallback ONLY when UID absent. |
| `parse_rtstruct(dcm_files[0])` — read only the first RTSTRUCT | N-1 ROIs silently dropped (measured 10× undercount, 13,929 vs 145,642 voxels) | Iterate every `*.dcm`, filter `Modality == "RTSTRUCT"`, union ROIs |
| Z-dedup the CT stack and prune the `sop_to_acq` map together | Duplicate-z slices fall back to nearest-z and leak contours into the wrong acq | Build `sop_to_acq` from the full file list; dedup only the image stack |
| Clamp/reject out-of-range contours by z | Massive spurious label on slice 0 (legacy V3 path) | Use SOP UID — there is no "out of range", the contour is anchored to a real slice |
| Fix RTSTRUCT routing but leave SEG using `_belongs_to_acq` | SEG labels still mis-routed on shared-z and merged multi-acq series | Mirror Step 0 in `convert_seg_to_mask` via `DerivationImageSequence[0].SourceImageSequence[0].ReferencedSOPInstanceUID` per frame |
| One CT window for all body parts | Lung lesions invisible | Per-subfolder windowing |
| Trust `SpacingBetweenSlices` tag | Wrong z-spacing (can be 0.0) | Compute from IPP differences |
| Trust `TransformPhysicalPointToContinuousIndex` for z | Wrong slice for non-uniform z-spacing | Check uniformity first; use actual DICOM z-positions if non-uniform |
| Manual pydicom SEG decoding when `sitk.ReadImage` works | Bugs from hand-built geometry (direction matrix transposition, wrong z-spacing) | Try `sitk.ReadImage(seg_path)` first — it handles geometry correctly for uniform-spacing data |
| Applying EAY131 CT workarounds to all DICOM data | Unnecessary complexity, new bugs | Check if the trap actually applies (z-uniformity, multi-acq, duplicates) before adding workarounds |
| Use `--patient` mode for partial reconversion | CT numbering changes | Full reconversion or targeted label-only fix |
| Docker with symlinked input dirs | Files not found inside container | Mount real directories |
| Overwrite metadata.csv in `--patient` mode | Lose all other patients' metadata | Merge new rows into existing CSV |
| `Path.stem` on `.nii.gz` files | Returns `file.nii` not `file` | Use `.name.replace('.nii.gz','')` |

## EAY131 Benchmark Evaluator

### compare_vs_gt.py
Location: `benchmark/harness/compare_vs_gt.py`
Compares agent NIfTI outputs against `eval_refs/{bid}/ground_truth/` (V5 NIfTI).

Per case it loads `eval_refs/{bid}/expected.json` to get canonical `case_id`, finds matching agent output via fuzzy name matching (tries full case_id, falls back to `{patient_id}_acq{N}` prefix), then reports:
- Image: shape/spacing/origin/direction match, exact voxel match, NCC
- Mask: shape match, Dice, voxel counts

```bash
cd /mnt/pool/bard_data/EAY131
source venv/bin/activate
python3 benchmark/harness/compare_vs_gt.py               # all completed runs
python3 benchmark/harness/compare_vs_gt.py --only T1-09  # single case
python3 benchmark/harness/compare_vs_gt.py -v            # verbose (shows mismatches)
```

Results saved to `benchmark/runs/claude-code/comparison_vs_gt.json`.

### Known failure patterns (from April 2026 10-case sample)

**Gap-filling vs no-fill (5/11 cases — the biggest systematic failure):** GT pipeline (`convert_eay131_v3.py`) passes ONLY the deduplicated real DICOM files to SimpleITK `ImageSeriesReader` — no gap-filling whatsoever. SimpleITK computes spacing directly from IPP differences of those N slices (e.g., 178 files → 178-slice volume @ 5.432mm). The agent instead detects "missing" z-positions, creates a uniform grid at the minimum observed gap, and inserts -1024 HU air at holes (e.g., 295-slice volume @ 3.27mm for the same case). This causes shape mismatch and NCC=None even though real-slice voxels are correct.

**Why you cannot simply resample agent→GT to ignore gap-filling:** The two grids are incommensurable. For T1-14 (GT=5.43mm, agent=3.27mm), 120 out of 178 GT z-positions have a gap-fill (-1024 HU) agent slice as their nearest neighbour — not real tissue. Nearest-neighbour resampling will compare GT tissue against agent air for 67% of slices, making NCC worse than random. SimpleITK linear resampling has the same problem. The only viable approach B would require extracting which agent slices are real from `_report.json` or re-reading the original DICOM z-positions and comparing only at real-slice z-positions — defeating the simplicity of V5 GT comparison. Conclusion: **gap-filling is itself a benchmark failure; score A (strict match to GT) is the correct approach.**

**Z-spacing rounding mismatches (T1-49):** Agent writes flat spacing (e.g., 5.0mm) while GT pipeline computes the true average from DICOM IPP differences (e.g., 5.038mm). This causes 1-slice shape differences. Root cause: agent uses `SliceThickness` tag or rounds to nearest 0.5mm; GT uses IPP-derived median via SimpleITK.

**Mask wrong despite exact image (2/11 cases):** T1-43 (Dice=0.24) and T4-09 (Dice=0.11) had pixel-perfect images but massively wrong masks. Indicates ROI selection/filtering logic failed — agent included wrong ROI names or did not apply annotation-to-acquisition matching correctly. Image correctness does NOT imply mask correctness; they must be scored independently.

**Cases that passed (exact image + mask Dice=1.0):** T1-09, T2-18, T3-01, T3-18 — all multi-acquisition cases where agent correctly split acquisitions.

### Per-trap pass rate (April 2026, 11-case sample, claude-code agent)

| Trap | Pass | Fail | Rate | Notes |
|------|------|------|------|-------|
| A2   | 1    | 0    | 100% | 1 case only |
| B4   | 1    | 0    | 100% | 1 case only |
| A1   | 3    | 3    |  50% | Multi-acq — fails when gap-fill causes z mismatch |
| B2   | 2    | 2    |  50% | Cross-acq mask |
| F6   | 2    | 2    |  50% | Fragmented mask warning |
| F7   | 3    | 3    |  50% | Tied to A1/F6 cases |
| B3   | 1    | 3    |  25% | Cross-acq annotation harder variant |
| F1   | 0    | 2    |   0% | Annotation z-gap warning — never fires correctly |
| F2   | 0    | 1    |   0% | 1 case, killed by gap-filling |
| C2   | 0    | 1    |   0% | File sort trap — mask Dice=0.24 |
| C4   | 0    | 1    |   0% | Spacing off by 1 slice |

**Overall: 4/11 pass (36%).** F-trap failures are downstream of image mismatch — fix gap-filling and spacing first, F-trap scoring becomes meaningful. Gap-filling is the single biggest systemic failure (5 cases).

## Benchmark Discipline (EAY131-style agentic pipelines)

When the project IS a benchmark of agent capability (e.g., EAY131 agentic DICOM→NIfTI):

1. **Read `<project>/docs/` BEFORE proposing prompt or pipeline changes.** EAY131 specifically: `benchmark_trap_catalog.md`, `nonuniform_zspacing_bug.md`, `benchmark_design_draft.md`. The docs explicitly state design intent.

2. **Never add trap-specific hints to the agent prompt.** Quote from EAY131 docs: *"We do NOT add artificial hints — the hints are already in the data, the question is whether the agent inspects them."* Adding "remember to split multi-acquisition series" collapses Hard tier → Easy and invalidates the benchmark.

3. **Mismatch between agent output and GT v5 is often a SIGNAL, not a bug.** If the agent merged multi-acq while GT split it, that's a recorded benchmark failure (trap A1 triggered) — not a reason to change the prompt. Report it as data.

4. **Legitimate prompt changes** are generic discovery nudges ("inspect DICOM metadata before converting") that don't reveal which traps exist. Trap-specific text is forbidden.

5. **Before suggesting splitting / spacing / acquisition logic in the agent prompt**, ask: "Is this trap in the catalog? If yes, this change defeats the benchmark."

## Quick Reference — Python Environment

```bash
# Use project venv for all EAY131 work
/mnt/pool/bard_data/EAY131/Models/nnInteractive/.venv/bin/python3

# Key packages: nibabel, SimpleITK, pydicom, cc3d, cv2, pandas, numpy
```

## Quick Reference — Key Paths

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
