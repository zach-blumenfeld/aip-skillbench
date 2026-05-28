# Upload a run-matrix campaign to HuggingFace

Reference for archiving an eval campaign as a private HuggingFace dataset, bundled with the campaign report and the repo README. Copy commands one block at a time — don't run the whole file blind.

## Fill these in

```bash
ORG=neo4j                       # your company HF org slug
CAMPAIGN=eval-1-haiku                     # dir name under runs/
DATASET=experiment-aip-skillbench-${CAMPAIGN}   # repo name under the org
```

## One-time prerequisites

Only do once per machine:

```bash
uv add huggingface_hub --dev
uv run hf auth login
# paste a Write-scoped token from https://huggingface.co/settings/tokens
```

## 1. Stage a copy of the campaign

Working off a copy keeps the original `runs/<campaign>/` intact. Run from the repo root.

```bash
STAGING=runs/_hf-staging-${CAMPAIGN}

rm -rf "$STAGING"
cp -R runs/${CAMPAIGN} "$STAGING"
```

## 2. Bundle the report and README

The eval report becomes the HuggingFace dataset card (HF renders `README.md` as the landing page). The repo-level README goes alongside for broader project context.

```bash
cp reports/${CAMPAIGN}.md "$STAGING/README.md"
cp README.md             "$STAGING/REPO-README.md"
```

## 3. (Optional) strip large recreatable artifacts

Cuts ~600 MB of `compressed_video.mp4` outputs from `video-silence-remover` cells. Skip if you want the full record uploaded.

```bash
find "$STAGING/cells" -name "compressed_video.mp4" -delete 2>/dev/null
find "$STAGING/cells" -name "install-stdout.txt"   -delete 2>/dev/null

du -sh "$STAGING"      # sanity check
```

## 4. Create the private dataset repo

One-time per campaign. Errors harmlessly if the repo already exists.

```bash
uv run hf repos create "$ORG/$DATASET" --repo-type dataset --private
```

(The new `hf` CLI takes the full `org/name` as a single argument — there's no separate `--organization` flag any more. `hf repo` still works but is deprecated in favor of `hf repos`.)

## 5. Upload

```bash
uv run hf upload "$ORG/$DATASET" "$STAGING" . \
  --repo-type dataset \
  --commit-message "Upload $CAMPAIGN ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
```

> If you skipped step 4, add `--private` here — `hf upload --private` auto-creates the repo as private when it doesn't yet exist (ignored if it already does).

## 6. Cleanup the staging dir

```bash
rm -rf "$STAGING"
```

## Browse

```
https://huggingface.co/datasets/$ORG/$DATASET
```

---

## How colleagues download

They each need to be a member of `$ORG` with at least `read` access and have run `hf auth login` once on their machine.

```bash
hf download $ORG/$DATASET \
  --repo-type dataset --local-dir ./$CAMPAIGN
```

In Python:

```python
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="$ORG/$DATASET",
    repo_type="dataset",
    local_dir="./$CAMPAIGN",
)
```

Direct read of `summary.csv` without downloading:

```python
import pandas as pd
df = pd.read_csv("hf://datasets/$ORG/$DATASET/summary.csv")
```
