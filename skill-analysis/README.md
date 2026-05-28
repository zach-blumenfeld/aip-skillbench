# skill-analysis

Profiles the **structure of every task's human-curated skill set** to support the *human-curated vs AIP-from-curated* study. Both modes carry the same domain knowledge — AIP just repackages it — so the question isn't "does AIP add knowledge" but "**does AIP-formatting the same human knowledge make an agent more successful, faster, and more consistent — and when does it help most?**"

The working hypothesis from the eval-3med deep dives: **AIP's benefit scales with how unstructured the human skill is.**
- `drone-planning-control` — human skill was **prose-only (0 scripts)**; AIP added executable scripts → large gain (5/5 @ 734 s vs 2/5 @ 1279 s).
- `crystallographic-wyckoff` — human skill had scripts but **~6,400 lines of prose/reference**; AIP compressed + structured it → consistency gain (±1.5 s vs a 138–255 s spread).
- A task whose human skill is *already* tight and scripted should show a *small* AIP gain — and confirming those nulls strengthens the paper.

So `structure_class` (below) is the proposed **primary axis for stratified task sampling**, with difficulty and category as secondary spread.

## Files

- `analyze_skills.py` — walks `vendor/skillsbench/tasks/<task>/environment/skills/`, measures skill structure, joins `task.toml` difficulty/category + `instruction.md` description.
- `skill-metrics.csv` — one row per task (regenerate any time).

Run from the repo root:

```bash
uv run python skill-analysis/analyze_skills.py
```

## Columns

| column | meaning |
|---|---|
| `task`, `difficulty`, `category`, `description` | task identity + `task.toml` metadata + first instruction sentence |
| `structure_class` | the AIP-upside axis — see below |
| `n_skills` | number of curated skill dirs (each with a `SKILL.md`) |
| `skill_names` | `;`-joined skill dir names |
| `skill_md_loc` | total lines across all `SKILL.md` files (procedure prose) |
| `n_scripts`, `script_loc` | count + total lines of executable files (`scripts/` dirs or code extensions) |
| `n_refs`, `ref_loc` | count + total lines of reference docs (`references/`, other `.md`/`.txt`) |
| `n_assets` | non-code, non-doc bundled files (data, images, templates) |
| `prose_loc` | `skill_md_loc + ref_loc` — total human-readable text the agent must absorb |
| `prose_to_code_ratio` | `prose_loc / script_loc` — high = prose-heavy (more AIP upside), blank if no scripts |
| `total_files`, `total_kb` | overall size of the skill set |

## `structure_class` (primary sampling axis)

| value | rule | predicted AIP-from-curated upside |
|---|---|---|
| `prose-only` | `script_loc == 0` | **highest** — no executable knowledge yet; AIP can add runnable scripts |
| `mixed` | `0 < script_loc < prose_loc` | medium — some scripts, but prose still dominates; AIP compresses + structures |
| `script-heavy` | `script_loc >= prose_loc` | **lowest** — already executable and terse; little for AIP to improve |
| `none` | `n_skills == 0` | n/a — no curated skill (none in the current corpus) |

## Current distribution (95 tasks)

- **prose-only: 50** · **mixed: 32** · **script-heavy: 13** · none: 0

All 95 tasks have at least one curated skill, so all are eligible for modes 2 (human-curated) and 5 (aip-from-curated). The corpus is **prose-heavy** — over half the tasks ship human skills with no executable code at all, which is exactly where the eval-3med results suggest AIP helps most.

## Suggested use

Sample the eval task set to span `structure_class` (prose-only / mixed / script-heavy) so the run can show the *gradient* of AIP benefit against human-skill structure, not just an average. Cross with `difficulty` and `category` for secondary coverage. Load in pandas:

```python
import pandas as pd
df = pd.read_csv("skill-analysis/skill-metrics.csv")
df.groupby("structure_class")[["prose_loc", "script_loc"]].median()
```
