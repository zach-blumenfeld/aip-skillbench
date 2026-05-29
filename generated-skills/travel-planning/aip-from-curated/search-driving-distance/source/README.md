# Source notes — `search-driving-distance` (AIP conversion)

This folder is the canonical source bundle for the AIP version of the
travel-planning `search-driving-distance` skill. It carries:

- `SKILL.md` — the original curated Agent Skill the AIP version was compiled from.
- `procedure.schema.json` — the AIP schema this skill validates against
  (bundled locally so the skill is self-contained, per AIP spec).

## Schema choice

Reused `procedure.schema.json` (no new schema authored). The skill is a single
deterministic execution graph: take origin / destination / mode in, run a
script that consults the bundled distance-matrix CSV, hand a parsed result
downstream. That is exactly the procedure-schema scope. Authoring a new
schema would create a single-skill schema family — an AIP anti-pattern.

## Step structure

Two steps:

1. `lookup-distance-cost` — **scripted**. The work is a deterministic CSV
   lookup with a fixed cost formula (`int(km * 0.05)` when mode contains
   `driving`, `int(km)` when mode equals `taxi`, otherwise no cost). Numeric
   thresholds and lookup tables are exactly what the AIP best-practices guide
   says to script. The script also handles the city-name parenthesis strip
   (`"Sedona (AZ)"` → `"Sedona"`), distance-string parsing (`"1,144 km"` →
   `1144.0`), and the multi-day suppression rule, so there is no separate
   normalize-input prose step.
2. `interpret-result` — **prose**. The script returns one of two shapes — a
   detailed `mode, from X to Y, duration: ..., distance: ..., cost: ...`
   line or a `no valid information.` line — and the agent has to *judge*
   which it got and how to react (consume the legs, retry with a different
   mode/spelling, or fall back to a different transport skill). That is
   interpretation, not mechanical branching, so it stays prose.

## Script

`scripts/search_driving_distance.py` is copied verbatim from the source
skill. It already resolves the dataset path via:

1. `/app/data/googleDistanceMatrix/distance.csv` (the container mount the
   task harness provides), then
2. a fallback relative to the script's own location.

We deliberately do **not** edit the path-resolution logic — the container
mount is the source-of-truth path during evaluation, and changing the
fallback would diverge from the curated skill the task expects. We also do
not strip the unused `subscription_key` / `gplaces_api_key` parameter or the
"online mode can still work" comment, even though the bundled script never
calls the Google API — preserving the surface area keeps the script
byte-identical to the curated source.

## Description rewrite

The frontmatter `description` is keyword-richer than the source (names the
bundled distance-matrix CSV explicitly, lists `driving` and `taxi` as the
two cost-bearing modes, mentions duration / distance / cost as the output
fields, and frames the skill as the ground-leg complement to
`search-flights`). The source description is preserved in `source/SKILL.md`.

## Deliberate drops

- The original `## Installation` (`pip install pandas numpy requests`)
  line is not carried into the AIP body. The task harness already provides
  `pandas` in the execution environment, and `numpy` / `requests` are not
  actually imported by the bundled script — `numpy` is transitively pulled
  by pandas and `requests` is a dead dependency from the original online
  mode. We surface the real runtime requirement (`pandas` and the mounted
  CSV) via the `compatibility` field instead.
- The Python `Quick Start` import example
  (`from search_driving_distance import GoogleDistanceMatrix`) is not
  carried into the AIP body. The AIP body documents the **CLI invocation**
  the agent will actually use
  (`python scripts/search_driving_distance.py --origin ... --destination ... --mode ...`);
  the Python-import path is redundant in the task's bash-tool execution
  environment.
