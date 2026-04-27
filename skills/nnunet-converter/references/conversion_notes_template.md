# Conversion Notes Template (MANDATORY Step 5)

After every successful conversion, append an entry to `conversion_notes.md` in the `nnUNet_raw/` directory. This file is the **only human-readable record** of how each dataset was prepared and what was intentionally excluded. **Do not skip this step.**

If `conversion_notes.md` does not exist in `nnUNet_raw/`, create it first with this header:

```markdown
# nnUNet Dataset Conversion Notes
```

Each entry must include all sections below — leave a placeholder if a value is unknown, do not silently omit fields.

## Entry template

```markdown
## Dataset{ID}_{Name}

**Source:** `/path/to/source/data/`
**Task:** brief description of the segmentation task
**Cases:** number of cases
**Dataset size:** total size on disk after conversion (e.g. 348 MB)
**Raw data format:** original format before conversion (e.g. DICOM, NIfTI, PNG, TIFF)
**Output format:** nnUNet file_ending (e.g. .nii.gz, .png, .tif)
**Conversion date:** YYYY-MM-DD
**Licence:** dataset licence if known (e.g. CC BY 4.0, TCIA Data Usage Policy)
**Paper:** citation or DOI of the related publication
**Webpage:** URL of the dataset page

### Format decision
- What format was the input? Was conversion needed? What tool/method was used?

### Label handling
- How were labels extracted/mapped? What are the integer values?
- Any special handling (remapping, combining, missing labels)?

### Dropped files
- What files from the source were NOT included and why?

### dataset.json
```json
channel_names: ...
labels: ...
file_ending: ...
```

### Notes
- Any gotchas, warnings, or non-obvious decisions made during conversion.
```

## Why this is mandatory

- Six months from now, the only way to know which cases were dropped (and why) is this file.
- Reviewers / collaborators need a single place to learn how each `Dataset{ID}_{Name}` was assembled.
- Compliance / licence tracking depends on the **Licence**, **Paper**, and **Webpage** fields being populated.

If you find yourself wanting to skip this step "because it's a small dataset" — do not. Five minutes now saves hours of forensic work later.
