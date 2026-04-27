# TCGA / GDC

Use `scripts/gdc_manifest.py` to generate a manifest, then `gdc-client` to
download the files in the manifest.

## Prerequisites

- `gdc-client` installed and on `$PATH`. If it isn't, tell the user to install
  it from <https://gdc.cancer.gov/access-data/gdc-data-transfer-tool> and stop.
- For **controlled** access, the user needs a dbGaP-approved token in a file
  pointed to by `GDC_TOKEN_FILE`. This skill defaults to `--access open` and
  does not manage tokens.

## Generating a manifest

```bash
python scripts/gdc_manifest.py \
    --project TCGA-CESC \
    --sample-type "Primary Tumor" \
    --data-format SVS \
    --preservation FFPE \
    -o cesc_manifest.txt
```

### Common filters

- `--project` — e.g. `TCGA-CESC`, `TCGA-PAAD`, `TCGA-TGCT`, `TCGA-PCPG`, `TCGA-UCS`.
- `--sample-type` — `"Primary Tumor"`, `"Solid Tissue Normal"`, `"Recurrent Tumor"`.
- `--data-format` — `SVS` (WSI), `BAM`, `VCF`, `TXT`, `TSV`.
- `--data-category` — `"Slide Image"`, `"Transcriptome Profiling"`, etc.
- `--preservation` — `FFPE` or `Frozen`.
- `--access` — `open` (default) or `controlled`. Controlled requires a token.

If the manifest comes back with **zero files**, the script errors out and
prints the filter payload — fix the filters and re-run.

## Downloading the files

Once the manifest exists:

```bash
gdc-client download -m cesc_manifest.txt -d $SCRATCH/datasets/CESC_wsi
```

Each file lands in **its own UUID-named subdirectory**. If the user wants a
flat layout, they post-process — do **not** flatten automatically, because the
UUID structure is what links files back to GDC metadata.

## Typical cohort sizes (set expectations)

- TCGA-CESC diagnostic slides FFPE: ~270 files, ~100 GB.
- TCGA-PAAD diagnostic slides FFPE: ~195 files, ~80 GB.
- TCGA-UCS diagnostic slides FFPE: ~57 files, ~20 GB.

Anything over ~5 GB should go through sbatch — read
`references/sbatch_template.md`.

## Common pitfalls

- Running `gdc-client` inside `$SLURM_TMPDIR`: the directory is wiped when the
  job ends. Use `$SCRATCH` for any download that needs to persist.
- Forgetting to set `--access controlled` when the user actually needs BAMs or
  raw sequencing — those are gated.
- Not setting `--preservation`: a TCGA cohort usually has both FFPE and Frozen
  slides; if the user wanted FFPE only, omitting the filter doubles the
  download.
