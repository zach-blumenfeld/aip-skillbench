# Source notes — `search-cities` (AIP conversion)

This folder is the canonical source bundle for the AIP version of the
travel-planning `search-cities` skill. It carries:

- `SKILL.md` — the original curated Agent Skill the AIP version was compiled from.
- `procedure.schema.json` — the AIP schema this skill validates against
  (bundled locally so the skill is self-contained, per AIP spec).

## Schema choice

Reused `procedure.schema.json` (no new schema authored). The skill is a single
deterministic execution graph: take a state name in, run a script that consults
the bundled dataset, hand the result downstream. That is exactly the
procedure-schema scope. Authoring a new schema would create a single-skill
schema family — an AIP anti-pattern.

## Step structure

Two steps:

1. `lookup-cities` — **scripted**. The work is a fixed lookup against a
   tab-separated dataset with case-insensitive matching. Deterministic, dataset
   bound, has a numeric/lookup-table character — exactly the kind of step the
   AIP best-practices guide says to script. The script also handles whitespace
   trimming and lowercasing internally, so there is no separate
   "normalize-state" prose step.
2. `interpret-result` — **prose**. The script returns one of three shapes
   (list of cities, the literal `"Invalid state."`, or
   `"No city data is available."`). The agent has to *judge* which shape it
   got and how to react (hand cities downstream, surface a recoverable input
   error, or escalate a missing-data fault). That is interpretation, not
   mechanical branching, so it stays as a prose step.

## Script

`scripts/search_cities.py` is copied verbatim from the source skill. It already
resolves the dataset path via:

1. `/app/data/background/citySet_with_states.txt` (the container mount the
   task harness provides), then
2. a fallback relative to the script's own location.

We deliberately do **not** edit the path-resolution logic — the container
mount is the source-of-truth path during evaluation, and changing the
fallback would diverge from the curated skill the task expects.

## Description rewrite

The frontmatter `description` is keyword-richer than the source (mentions
"U.S. states", names the downstream skills it gates, and calls out validation
vs. expansion). The source description is preserved in `source/SKILL.md`.

## Deliberate drops

- The original `## Installation` (No external dependencies) and Python
  `Quick Start` import example are not carried into the AIP body. The AIP
  body documents the **CLI invocation** the agent will actually use
  (`python scripts/search_cities.py --state ...`); the Python-import path is
  redundant in the task's bash-tool execution environment.
