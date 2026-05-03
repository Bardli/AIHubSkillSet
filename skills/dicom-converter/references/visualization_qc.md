# Visualization and QC Patterns

How to visually verify segmentation pipelines — from per-case overlay PNGs to grid videos and AI-assisted visual review.

## Segmentation overlay PNG (3-panel)

Use this when you want a per-case visual diff of GT vs prediction, across N sampled cases. Output is 100 PNGs of `image | image+GT (green) | image+pred (red)` that you can flip through manually or feed to an LLM for review.

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
    """Percentile-based normalization for MRI (no HU)."""
    p1, p99 = np.percentile(vol, 1), np.percentile(vol, 99)
    return np.clip((vol - p1) / (p99 - p1 + 1e-8), 0, 1)

def best_slice(gt, pred):
    """Pick the slice with the most foreground in EITHER GT or Pred.
    IMPORTANT: use max(GT ∪ Pred), NOT just max(Pred) — otherwise GT
    appears empty on the displayed slice (a visualization artifact that
    misleads the reviewer into thinking the model has no GT to compare).
    Flagged by Claude Code visual QC review (April 2026)."""
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
```

For T2 MRI use percentile normalization (`window_mri` above). For CT, swap in `ct_window_uint8` from `downstream_stages.md` with a body-part-appropriate window.

## AI visual review with Claude Code

After generating overlays, fire a separate Claude Code instance with extended thinking to review all N images and produce a structured report.

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

claude --model claude-opus-4-7 --effort max \
    -p "$(cat /tmp/qc_prompt.md)" \
    --allowedTools 'Read,Bash' \
    --add-dir /tmp/seg_overlays \
    --max-turns 30 \
    2>&1 | tee /tmp/qc_output.txt
```

### Pitfalls

- **Silent thinking phase.** With `--effort max` and 100 images, Claude Code stays silent for 3–5 minutes during extended thinking before any output. Do not kill the process — `wc -c /tmp/qc_output.txt` tells you if output has started.
- **Wrong slice selection.** `best_slice` MUST use `max(GT ∪ Pred)`. Using `max(Pred)` causes the GT panel to show empty masks, making the reviewer unable to compare. Real bug, real review caught it.
- **MRI vs CT.** For T2 MRI, use percentile normalization, not HU windowing. The reviewer LLM cannot tell the difference visually if you misnormalize, but the verdict will be wrong because contrast is broken.

### What to expect

- The reviewer LLM will categorize failures into types (over-segmentation, false positives, shape distortion).
- It will estimate production-readiness and a volumetric DSC.
- It will recommend immediate fixes (e.g., largest-connected-component post-processing).
- It may flag visualization artifacts (e.g., the empty-GT-panel bug above) — take these seriously, they often indicate real pipeline issues.

## Per-case review video (left CT, right CT+GT overlay)

For converted nnU-Net-style datasets, prefer the bundled helper:

```bash
python scripts/make_overlay_qc_videos.py \
    --dataset-dir /path/to/nnUNet_raw/Dataset123_Name \
    --output-dir /path/to/qc_videos \
    --num-samples 5 \
    --seed 42
```

The helper reads 3D SimpleITK-readable volumes (`.nii.gz`, `.mha`, `.nrrd`) from
`imagesTr/*_0000` and `labelsTr/*` by default, writes one MP4 per sampled case,
and uses robust percentile normalization unless CT windowing is explicitly
requested with `--modality CT --window-level ... --window-width ...`.
For multi-modal datasets, render another channel with `--channel 1`, `--channel
2`, etc. For a recovered failed case, render it separately with `--case-id
<case_id>`; do not rely on the random sample to catch it. Use `--num-samples` to
increase or reduce the random baseline sample count.

```python
PANEL = 384; HEADER_H = 40; FPS = 15; ALPHA = 0.45
# For each slice z:
#   Left panel: windowed CT (grayscale)
#   Right panel: CT + green overlay + white contours
#   Header: case_id, slice number, DSC if available
#   Color-code header by DSC: red < 0.3, orange < 0.5, yellow < 0.7, green ≥ 0.7
```

Generate with `imageio` or `cv2.VideoWriter`. Encode as MP4 (`mp4v` or `h264`) for portability.

## Side-by-side comparison (before/after fix)

Three panels: `CT | Version A | Version B`. Header shows `SAME` (green) or `DIFF` (orange) per slice — useful for confirming a fix didn't change unrelated slices.

## Grid QC video (10×5 grid, 50 cases)

Scroll through z simultaneously across 50 cases. Flag cells with red border + DSC label for low-scoring cases. Useful when you have many cases and want to spot systematic patterns at a glance.

## Dataset-selection / QC workflow

1. **Initial selection** → generate per-case videos → manual review.
2. **Mark bad cases** → exclude, pick candidates from pool.
3. **Generate candidate videos** → review → approve/reject.
4. **Track everything in CSVs**: `selection.csv`, `candidates.csv`, `exclude.csv`, `bad_cases.csv`.
5. **No wholebody in cancer-type selections** — replace with single-subfolder candidates (project-specific rule for EAY131-style cohorts).

### Pool priority (for replacements)

`referenced > unreferenced > global_exclude` — prefer cases that are already cited by the protocol over arbitrary additions, and only ever fall through to global_exclude as a last resort with explicit justification.
