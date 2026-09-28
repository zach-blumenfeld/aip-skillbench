# Upload a run-matrix campaign to HuggingFace

Use `scripts/hf_upload.py`. It stages nothing, scans everything it would ship for
credentials, and refuses to upload if it finds any.

## One-time setup

```bash
uv add huggingface_hub --dev
uv run hf auth login    # paste a Write-scoped token from https://huggingface.co/settings/tokens
```

## Upload

```bash
uv run python scripts/hf_upload.py --campaign eval-1-haiku --dry-run   # scan only
uv run python scripts/hf_upload.py --campaign eval-1-haiku             # scan, then upload
```

Defaults: private repo named `neo4j/experiment-aip-skillbench-<campaign>`, with
`reports/<campaign>.md` as the dataset card. Override with `--org`, `--dataset`, `--public`.
It also uploads the repo README as `REPO-README.md`.

Exit codes: `0` clean, `1` findings need review, `2` bad usage — safe to wire into CI.

**Agent trajectories (`acp_trajectory.jsonl`) are uploaded** — they are research data.
Safety comes from the scan, not from withholding them. Pass `--exclude-trajectories` to
drop them. Video and `install-stdout.txt` artifacts are always excluded as bulky and
recreatable.

## When it blocks

You get the file, line number, pattern name, and a masked value for every finding, plus a
report at `.secret-scan/<campaign>.txt` (gitignored). Every context window in that report is
sanitized, so reading it cannot re-expose a secret.

Then pick one:

1. **False positive** — tighten `SECRET_PATTERNS` in the script.
2. **Real credential** — **revoke it first**, then redact in place
   (`scratch/redact-leaked-key.md`) and re-run. Redaction keeps trajectories analytically
   whole: the secret becomes `[REDACTED_ANTHROPIC_API_KEY]` and nothing else changes.
3. **Traces you don't need** — re-run with `--exclude-trajectories`.

Never bypass by deleting the check.

## Tuning the patterns

`SECRET_PATTERNS` is calibrated against the whole corpus: it catches the 2026-09-02
`civ6-adjacency-optimizer` leak with zero false positives across ~1,100 trajectory files in
four clean campaigns. Preserve these two if you edit it:

- The generic rule matches `API_KEY=`, **not** `_KEY=`. `GPG_KEY=` is a public signing
  fingerprint present in every env dump and would otherwise fire constantly.
- `hf_` requires 30+ following chars. A bare `hf_` substring matches ordinary identifiers
  like `hf_hub_download` and `hf_with_ppo` — that produced 46 spurious hits during triage.

## Background: why the gate exists

On 2026-09-02 the `civ6-adjacency-optimizer` task shelled out to `env`, capturing the
container environment — including a live `ANTHROPIC_API_KEY` — into its console output and
from there into `acp_trajectory.jsonl`. The key was published in two public datasets and
drained before discovery. Console capture is unbounded by design, so trajectories cannot be
assumed safe without inspection. See `scratch/` for the incident runbooks.

One trap worth knowing if you ever scan by hand: inside a Claude Code session `grep` is a
shell function that honors `.gitignore`, and `runs/` is gitignored — a bare `grep` scans
*nothing* and reports a false all-clear. Use `find … -print0 | xargs -0 /usr/bin/grep`.
This masked the original leak during triage.

## Browse

```
https://huggingface.co/datasets/<org>/<dataset>
```

## How colleagues download

They need membership in the org with at least `read` access, and `hf auth login` once.

```bash
hf download neo4j/experiment-aip-skillbench-eval-1-haiku \
  --repo-type dataset --local-dir ./eval-1-haiku
```

```python
from huggingface_hub import snapshot_download
snapshot_download(repo_id="neo4j/experiment-aip-skillbench-eval-1-haiku",
                  repo_type="dataset", local_dir="./eval-1-haiku")
```

Direct read of `summary.csv` without downloading:

```python
import pandas as pd
df = pd.read_csv("hf://datasets/neo4j/experiment-aip-skillbench-eval-1-haiku/summary.csv")
```

## Manual upload (fallback only)

For a partial or one-off upload the script doesn't cover. **Run the gate first** —
`--dry-run` on the campaign — then:

```bash
ORG=neo4j; CAMPAIGN=eval-1-haiku; DATASET=experiment-aip-skillbench-${CAMPAIGN}

uv run hf upload "$ORG/$DATASET" "runs/$CAMPAIGN" . \
  --repo-type dataset --private \
  --exclude "**/compressed_video.mp4" --exclude "**/install-stdout.txt" \
  --commit-message "Upload $CAMPAIGN"

uv run hf upload "$ORG/$DATASET" "reports/${CAMPAIGN}.md" README.md --repo-type dataset
```

`hf upload --private` auto-creates the repo if it doesn't exist. `--exclude` takes globs,
not regex, and is a **repeatable flag** — one pattern per `--exclude`. Two globs after a
single flag would be parsed as a positional argument, not a second pattern.
