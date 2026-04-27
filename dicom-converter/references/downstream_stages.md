# Downstream Stages — NIfTI → NPZ and Inference

After Stage 1 (DICOM → NIfTI) is correct, downstream packing and inference are mostly mechanical. This reference collects the gotchas that have actually bitten in production.

## Stage 2 — NIfTI → NPZ

### CT windowing per body part

Wrong windowing destroys contrast. An abdomen window applied to a lung scan makes lesions invisible.

| Body part | Level (HU) | Width (HU) | Use for |
|---|---|---|---|
| Abdomen | 40 | 400 | Liver, kidney, pancreas, colon |
| Chest | -600 | 1500 | Lung parenchyma + mediastinum |
| Pelvis | 40 | 400 | Rectum, pelvic organs |
| Bone | 400 | 1800 | Bone metastases |

```python
import numpy as np

def ct_window_uint8(data, level, width):
    """Apply CT window/level and convert to uint8 [0, 255]."""
    lo = level - width / 2
    hi = level + width / 2
    return ((np.clip(data, lo, hi) - lo) / (hi - lo) * 255).astype(np.uint8)
```

Pick the window from a per-subfolder map (cancer type, anatomy) — never a single window for the whole dataset.

### NPZ format (MedSAM2 / EfficientMedSAM2 conventions)

```python
import numpy as np

np.savez_compressed(
    path,
    imgs=ct_uint8,          # (Z, Y, X) uint8 — windowed CT (or other modality)
    gts=instance_labels,    # (Z, Y, X) uint8 — instance labels via cc3d connectivity=26
    recist=recist_lines,    # (Z, Y, X) uint8 — LD lines on key slice (optional)
    spacing=spacing,        # (3,) float64 — (x, y, z) mm
    direction=direction,    # (9,) float64 — flattened 3x3 direction matrix
    origin=origin,          # (3,) float64 — (x, y, z) mm
)
```

`gts` should be **instance** labels (1 per connected component), not semantic labels. Use `cc3d.connected_components(mask, connectivity=26)`.

### Common Stage 2 mistakes

- Windowing before label routing — slice indexing is unaffected by windowing, but if you're computing instance labels post-window, always do connected components on the binary mask, not on the windowed image.
- Storing `spacing` as `(z, y, x)` instead of `(x, y, z)` — most downstream consumers assume `(x, y, z)`. Stick with one convention and document it.
- Saving `imgs` as `float32` instead of `uint8` — bloats the NPZ and breaks downstream tooling that expects uint8.

## Stage 3 — Inference

### Docker GPU fix (ALL competition images)

ALL competition Docker images observed in 2025–2026 hardcode `CUDA_VISIBLE_DEVICES=""`. Without the fix below, you get CPU-only inference at 3+ hours per case. With the fix: minutes per case.

```bash
docker run --rm --gpus "device=$GPU" \
    -e CUDA_VISIBLE_DEVICES=0 \
    -v "$INPUT":/workspace/inputs:ro \
    -v "$OUTPUT":/workspace/outputs \
    "$IMAGE":latest \
    /bin/bash -c "
        for f in *.py; do
            sed -i \"s/os.environ\['CUDA_VISIBLE_DEVICES'\] = ''/os.environ['CUDA_VISIBLE_DEVICES'] = '0'/\" \"\$f\"
            sed -i \"s/device='cpu'/device='cuda'/g\" \"\$f\"
        done
        python3 \$SCRIPT --imgs_path /workspace/inputs --pred_save_dir /workspace/outputs
    "
```

**Verify the fix actually applied:**
- `nvidia-smi` should show > 2 GB GPU memory and > 50% utilization.
- If you see ~ 15 MB and 4% util, the `sed` did not match the actual code (the upstream image changed the env-var write style). Inspect the image's Python files and adjust the `sed` patterns.

**Docker symlinks do not work.** Mount real directories, not symlink splits — the bind mount sees the symlink target via mount-namespace rules and you usually end up with empty input directories inside the container. Resolve symlinks before mounting.

### Common Stage 3 mistakes

- Forgetting `--gpus "device=$GPU"` and relying on `--gpus all`. On shared multi-GPU hosts, this overcommits and the container fails or is slow.
- Mounting the same path read-write when read-only is enough. Use `:ro` for inputs to catch bugs that try to write into the mount.
- Assuming the image's entrypoint script honours your `CUDA_VISIBLE_DEVICES=0` env var. Many of them re-set it from inside the script. The `sed` patches the script source, which is the only thing that actually works.
