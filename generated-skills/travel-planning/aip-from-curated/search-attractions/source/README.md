# source/ — search-attractions AIP conversion notes

## Source materials

- `ORIGINAL_SKILL.md` — the curated Agent Skill this AIP version was compiled from
  (`vendor/skillsbench/tasks/travel-planning/environment/skills/search-attractions/SKILL.md`).
- `procedure.schema.json` — bundled copy of the AIP procedure schema this skill
  validates against. Pinned to `v0.3a3`.

## Schema choice

Reused the canonical **procedure** schema (`procedure.schema.json`). Search-attractions
is a one-step data lookup, but the procedure schema is the right fit:

- It frames the skill as a script-backed execution graph, which is exactly what this
  skill is (CLI invocation against a bundled CSV).
- It has first-class `steps[].script`, `inputs`, and `outputs` for declaring the
  contract between the agent and `scripts/search_attractions.py`.
- It carries the `anti_patterns` and `scenarios` slots used to encode the
  case-insensitive city match, the two distinct sentinel string responses, and
  the data-from-skill-not-memory rule from the parent travel-planning task.

No new schema was drafted.

## Script vs prose decisions

All deterministic logic lives in `scripts/search_attractions.py` (copied verbatim
from the curated skill, no behavior changes). This includes:

- CSV path resolution (container `/app/data` first, then repo-relative fallback).
- Column projection, `dropna`, and `City` whitespace normalization.
- Case-insensitive city match.
- Sentinel string responses for empty dataset / no-match-for-city.
- Argparse CLI surface (`--city`, `--path`).

The prose `extract-city` step is intentionally **not** scripted — picking the
right city name out of an itinerary request is interpretive (resolving "Cleveland,
OH" → "Cleveland", choosing which of three Ohio cities to query next), which is
exactly the case the AIP spec calls out for prose over script.

## Body drops

Nothing dropped. The curated `SKILL.md` is tiny (a `pip install` line plus a
Python Quick Start). The AIP body absorbs both — install requirements move to
`compatibility` frontmatter, and the Quick Start is replaced by the CLI
invocation expected by the parent task's container runtime (`/app/data/...`).
The Python-import usage path from the original is preserved in a scenario for
agents that prefer importing the module over shelling out.
