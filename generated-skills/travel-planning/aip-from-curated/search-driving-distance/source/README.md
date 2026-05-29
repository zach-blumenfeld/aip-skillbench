# Source notes — search-driving-distance (AIP transition)

## Origin

Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-driving-distance/`.

The source skill is minimal: a tiny `SKILL.md` (install + quickstart) and one
Python script (`scripts/search_driving_distance.py`) that wraps a bundled
distance-matrix CSV.

## Schema choice

Picked the shared **procedure** schema
(`https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`).
The skill is a tight lookup workflow — parse inputs, run the backing script,
interpret the result — which is exactly the procedure shape: a small DAG of
script-backed nodes with typed inputs/outputs.

## Mapping decisions

- The original `SKILL.md` contained two prose blocks: a `pip install` line and
  a Python quickstart. Both are folded into the AIP body's
  `compatibility` and into `steps[*].script` references — the CLI form is
  preferred (no Python import needed by the consuming agent).
- The bundled CSV at `data/googleDistanceMatrix/distance.csv` lives in the
  task environment, not the skill. The script resolves it via
  `/app/data/googleDistanceMatrix/distance.csv` (container) and otherwise
  `<skill>/../../data/googleDistanceMatrix/distance.csv` (workspace). Kept the
  resolver as-is so the script stays drop-in compatible with the source task.
- Cost rules (`driving` → `0.05 * km`, `taxi` → `1.0 * km`) and the
  "duration containing 'day' → no valid result" guard are domain logic, so
  they stay encoded in the script (per AIP best practices on scriptable
  logic).
- City-name normalization (stripping a trailing parenthetical, e.g.
  `"Seattle (WA)"` → `"Seattle"`) is also in-script.

## Deliberate drops

- The original `pip install pandas numpy requests` line is preserved in
  `compatibility`. `numpy` and `requests` are not actually used by the script
  — pandas is the only hard dep — but the AIP body retains the full list to
  mirror the source environment's expectations.
- The original Python `from search_driving_distance import GoogleDistanceMatrix`
  quickstart is dropped from the body in favor of the CLI invocation
  (`uv run scripts/search_driving_distance.py …` / `python scripts/...`),
  which is simpler for an autonomous agent to invoke without configuring
  `PYTHONPATH`. The class-level API is still available via the unchanged
  script for any consumer that imports it.
