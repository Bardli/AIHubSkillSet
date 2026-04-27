# Google Drive (`gdown`)

Use `gdown` for downloads from Google Drive.

## Prerequisites

- `gdown` installed (`pip install gdown`). If not, install it.
- The link must be **public or "anyone with link"-shared**. Private files
  require Drive API + OAuth, which is **out of scope for this skill** — tell
  the user and stop.

## Commands

```bash
# Single file (paste the share URL or just the file id)
gdown <file-url-or-id>

# Public/shared folder
gdown --folder <folder-url>
```

## Known limits

- **No reliable resume.** If a large download dies mid-way, you usually have to
  re-pull from scratch. `gdown` may recover small interruptions; large transfers
  rarely recover gracefully.
- **Google rate limits popular files.** The error message is "Too many users
  have viewed or downloaded this file recently." The only workarounds are
  (a) wait 24 hours, or (b) ask the file owner for a fresh share link. This
  skill cannot fix it.
- **Private / restricted folders** need the Drive API with OAuth. Out of scope.
- **Folder downloads can silently truncate** at ~50 files for some folder
  layouts. If the user reports a missing-files complaint, count the files
  downloaded vs the folder's posted count.

## When to prefer something else

For anything over a few GB or for production use, prefer a stable source if
one exists (TCGA, HF, dedicated dataset host). Drive is fine for one-off pulls
of small artifacts (model weights, supplementary CSVs, paper figures), but it
is the worst of the four sources for large medical datasets.

## Common pitfalls

- Dropping `--folder` when the URL points to a folder: `gdown` downloads the
  HTML landing page, not the contents. Always include `--folder` for folders.
- Using a private Google Drive link copied from an org account where the user
  is logged in: the link will look public to them but be restricted to others
  / to `gdown`. Test the URL in an incognito window before scripting it.
