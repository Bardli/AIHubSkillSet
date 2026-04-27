# Kaggle

Use the `kaggle` CLI for both competitions and datasets.

## Prerequisites

- `~/.kaggle/kaggle.json` exists and is `chmod 600`. If not, **stop** and tell
  the user to create one from kaggle.com → Account → API → "Create New API
  Token", and to `chmod 600` it after placing it.
- `kaggle` CLI installed (`pip install kaggle`). If not, install it.
- **For competitions:** the user must have clicked "I accept the rules" on the
  competition page in a browser. Without that, `kaggle competitions download`
  silently returns a 403. **Always mention this before running.**

## Commands

### Competition

```bash
kaggle competitions download -c <competition-slug> -p <dest>
```

Outputs a single zip file at `<dest>/<slug>.zip`. The `--unzip` flag does NOT
work for competitions — unzip manually:

```bash
unzip <dest>/<slug>.zip -d <dest>/
rm <dest>/<slug>.zip
```

### Dataset

```bash
kaggle datasets download -d <owner>/<dataset-name> -p <dest> --unzip
```

`--unzip` works here. The dataset format is always `<owner>/<name>`.

## Examples

```bash
# RSNA Pneumonia Detection competition
kaggle competitions download -c rsna-pneumonia-detection-challenge \
    -p $SCRATCH/datasets/rsna_pneumonia

# A user-submitted dataset
kaggle datasets download -d kmader/finding-lungs-in-ct-data \
    -p $SCRATCH/datasets/lung_ct --unzip
```

## Common pitfalls

- 403 errors on a competition: the user has not accepted the rules. Send them
  to the competition page and stop.
- 401 errors: the API token has expired or `kaggle.json` is missing.
- Forgetting `--unzip` on a dataset and ending up with `.zip` files. (For
  competitions the inverse — passing `--unzip` does nothing useful.)
- Hitting the Kaggle API rate limit on rapid retries. There's no useful
  workaround other than waiting.
