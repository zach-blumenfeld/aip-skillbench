# Source notes — csv-processing → AIP

## Origin

Curated agent skill at
`vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/csv-processing/SKILL.md`,
mounted into the ACC simulation task to give the agent pandas idioms for
reading `sensor_data.csv` and writing `simulation_results.csv`.

## Schema choice

Reused `procedure.schema.json` (v0.3a2) — the schema fits a workflow of
"read → inspect → access → build → write" with per-step inputs/outputs. No
new schema drafted.

## Body shape

- `name` preserved verbatim — the task mounts the skill by directory name.
- `description` kept close to the source (read sensor CSV, write simulation
  CSV, handle missing values, time-series with pandas) so trigger keywords
  for this task stay intact.
- `steps` = the canonical CSV I/O lifecycle for this task, one node per
  conceptual concern. The simulation loop wires these together; no step is
  branch-heavy enough to warrant a backing script.
- `scenarios` ground each pattern in concrete ACC task data
  (`sensor_data.csv` columns, the exact `simulation_results.csv` column
  order, the `'cruise'` mode mapping when `lead_speed` is NaN).
- `anti_patterns` capture the easy-to-miss mistakes the source `SKILL.md`
  implies (forgetting `na_values`, omitting `index=False`, using sentinel
  values instead of `None`).
- The verbatim pandas code patterns live in
  `references/pandas-patterns.md` — loaded on demand, keeps the body lean.

## No scripts/

The source `SKILL.md` is a collection of pandas **idioms the agent copies
into its own simulation code** (`pid_controller.py`, `acc_system.py`,
`simulation.py`). They are not stand-alone runtime steps the skill
executes. The "Prioritize `scripts/`" rule applies to runtime
decisions/lookups/calculations the skill itself performs — not to code
snippets the agent integrates into its own files. Adding wrapper scripts
here would obscure the intended pattern (copy-and-adapt) without removing
any branching from the body.

## Source-to-body mapping

| Source section              | AIP body location                                       |
|-----------------------------|---------------------------------------------------------|
| Reading CSV                 | `steps[read-csv]` + `references/pandas-patterns.md`     |
| Handling Missing Values     | `steps[handle-missing]` + scenarios + anti_patterns     |
| Accessing Data              | `steps[access-data]` + `references/pandas-patterns.md`  |
| Writing CSV                 | `steps[write-csv]` + scenarios + anti_patterns          |
| Building Results Incrementally | `steps[build-results]` + scenarios                  |
| Common Operations           | `references/pandas-patterns.md` (loaded on demand)      |

No source content deliberately dropped.
