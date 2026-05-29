# Source notes — search-accommodations (AIP)

## Origin

Converted from the curated SkillsBench skill at
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-accommodations/`.

The original `SKILL.md` is a minimal stub (description + install snippet + 4-line
quick-start). The real expertise sits in `scripts/search_accommodations.py`,
which handles dataset path resolution, column cleaning, case-insensitive city
matching, and CLI invocation.

## Schema choice

`procedure.schema.json` — this skill is a small, linear execution graph:
resolve the requested city → run a script-backed lookup → present results. No
new schema needed.

## Step design (script vs. prose)

- **`lookup-accommodations` is scripted.** All the deterministic work lives in
  `scripts/search_accommodations.py`: data path resolution
  (container `/app/data/...` first, then dataset-relative fallback), column
  selection, NaN drop, string normalization, case-insensitive match, and the
  two empty-result sentinel strings. Encoding any of that as prose would just
  invite drift.
- **`resolve-city` and `present-results` are prose.** Both depend on
  interpreting the agent's current context: which city the user means
  (disambiguation, parsing free-form requests), and how the results should be
  surfaced (full table vs. top-N, filtering by price/rating before recommending,
  whether to mention the no-results sentinel verbatim or rephrase). These are
  judgment calls, not lookup logic.

## Files

- `scripts/search_accommodations.py` — copied verbatim from the source skill.
  Importable (`from search_accommodations import Accommodations`) and runnable
  as a CLI (`python scripts/search_accommodations.py --city Seattle`).
- `source/ORIGINAL_SKILL.md` — original SKILL.md preserved for reference.
- `source/procedure.schema.json` — bundled AIP schema this skill validates
  against.

## Deliberate drops

- Original `## Installation` block (`pip install pandas`) — environment setup
  is handled by the task harness, not by the agent at activation time. Captured
  in `compatibility` frontmatter instead.
- Original `## Quick Start` Python snippet — superseded by the structured
  `scenarios` and step graph in the AIP body, which give the agent the same
  call pattern plus the why and the gotchas.

## Mapped content

Every behaviour the source script exhibits is captured in the AIP body or
visible to the agent through the bundled script:

- City lookup is case-insensitive (script + step description).
- Default dataset path tries `/app/data/...` first, then the repo-relative
  fallback (script; surfaced as an anti-pattern against hard-coding paths).
- Empty-result sentinels ("There are no accommodations in this city." /
  "No accommodations data is available.") (script; surfaced to the agent via
  `present-results` so it knows to recognise rather than reinvent them).
- Returned columns are limited to the lodging-relevant subset (script; noted
  in `lookup-accommodations` outputs description).
