# source/ — AIP conversion notes for search-attractions

## Origin

Adapted from the curated Agent Skill at
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-attractions/`
(part of the SkillsBench `travel-planning` task fixture).

The original skill is minimal: a one-paragraph `SKILL.md` plus a single Python
script (`scripts/search_attractions.py`) that loads
`/app/data/attractions/attractions.csv` and returns the rows matching a given
city (case-insensitive exact match).

## Schema choice

Reuses the shared `procedure.schema.json`
(`https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`).
The skill is a small, mostly-linear procedure (normalise city → run lookup →
interpret result) — a perfect fit for the procedure schema. No new schema was
drafted.

## Files in this skill

- `SKILL.md` — AIP-format skill, body validated against the bundled schema.
- `scripts/search_attractions.py` — copied verbatim from the source skill; this
  is the source of truth for the lookup logic and is invoked by the procedure.
- `source/procedure.schema.json` — bundled copy of the AIP procedure schema.
- `source/SKILL.md` — the original curated `SKILL.md` for reference.

## Content classification (source → AIP body)

- "Retrieve attractions by city from the bundled dataset" → `purpose` +
  `trigger_when[0]`.
- "Use this skill when surfacing points of interest or building sightseeing
  suggestions for a destination" → `trigger_when` entries.
- `pip install pandas` install hint → `compatibility` frontmatter (runtime
  requirement) and a gotcha in `anti_patterns`.
- Python `Attractions().run(city)` quick-start → represented as a `script`-backed
  step (`query-attractions`) invoking `scripts/search_attractions.py --city`,
  which is the CLI surface of the same class. The CLI form is preferred for
  agent invocation (no Python session required).
- Edge-case return strings (`"No attractions data is available."`,
  `"There is no attraction in this city."`) → captured in the
  `interpret-results` step description and `anti_patterns` so the agent does
  not hallucinate attractions when the dataset returns nothing.

No source content was dropped.
