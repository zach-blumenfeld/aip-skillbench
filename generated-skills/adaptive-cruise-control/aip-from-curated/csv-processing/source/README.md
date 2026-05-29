# csv-processing — AIP conversion notes

## Source
`original-SKILL.md` is the curated SkillsBench skill verbatim from
`vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/csv-processing/SKILL.md`.

It documents Python / pandas patterns the agent should follow when reading
`sensor_data.csv` and writing `simulation_results.csv` in the Adaptive Cruise
Control task.

## Schema choice
`procedure.schema.json` — this is a structured procedure for reading,
filtering, and writing tabular data with pandas. Each pattern (read with NA
handling, scalar-vs-column NaN tests, filter / iterate, write with blank
cells for missing values) maps cleanly onto a step with inputs/outputs.

## Script vs prose vs assets
The skill is consumed by an agent that **writes its own Python code** (e.g.,
`simulation.py`). The agent does not invoke this skill at runtime — it adapts
the patterns into its own files. Same shape as the sibling `yaml-config`
skill in this task.

That makes `assets/` the right home for the code patterns, not `scripts/`:

- `assets/read_csv.py` — read template with `na_values=['', 'NA', 'null']`
  and a `missing_summary` helper.
- `assets/write_csv.py` — write template for both dict-of-columns and
  list-of-records styles, with `index=False` and None → blank cell behavior.
- `assets/access_data.py` — column selection, time-window filtering,
  `notna()` masks, scalar `pd.isna()` checks, per-row iteration that yields
  Python `None` for NaN lead values (matching the cruise-vs-follow branch
  in `acc_system.py`), and a `column_stats` helper for `acc_report.md`.

The steps in `SKILL.md` are prose nodes that point at these templates; there
is no `scripts/` because no step's logic is a deterministic transform the
skill itself needs to execute on structured inputs.

## Source-to-body mapping
Every distinct piece of `original-SKILL.md` is captured below.

| Source content | Where it landed |
|----------------|-----------------|
| `pd.read_csv` + `head` / `columns` / `len` inspection | `read-csv` step + `assets/read_csv.py` |
| `na_values=['', 'NA', 'null']` | `read-csv` step description + `read_csv.py` + anti-pattern on default NA list |
| `df.isnull().sum()` missing-value check | `read-csv` step + `missing_summary` helper |
| `pd.isna(row['column'])` scalar test | `access-data` step description (scalar idiom) + `iterate_sensor_rows` in `access_data.py` |
| Single / multi-column selection (`df['c']`, `df[['c1','c2']]`) | `access-data` step + `select_columns` helper |
| Boolean row filter incl. compound `&` mask | `access-data` step + `filter_time_window` helper |
| `df[df['column'].notna()]` mask | `access-data` step + `filter_not_null` helper |
| `pd.DataFrame(dict).to_csv(..., index=False)` | `write-csv` step + `write_csv_from_dict` in `write_csv.py` |
| Build list-of-dicts in a loop, then DataFrame → CSV | `write-csv` step + `write_csv_from_records` in `write_csv.py` |
| Statistics (`mean`, `max`, `min`, `std`) | `access-data` step + `column_stats` helper |
| Add computed column (`df['diff'] = df['a'] - df['b']`) | `access-data` step + `add_diff_column` helper |
| `df.iterrows()` per-row iteration | `access-data` step + `iterate_sensor_rows` helper |

Nothing from the original was dropped.

## Notable additions over the original
- **Anti-pattern list.** Explicit callouts on the defaults that bite in this
  task: pandas's default NA list does not catch `'NA'` / `'null'`; `index=False`
  is required so the output matches the task's column order; `None` (not the
  string `'None'`) is what becomes a blank cell.
- **None ↔ NaN bridging in `iterate_sensor_rows`.** The ACC task's
  `acc_system.py` branches on `lead_speed is None` for cruise vs follow mode,
  but pandas hands you NaN. The helper translates at the row boundary so the
  agent's downstream code stays clean. The original SKILL.md hinted at
  `pd.isna(row['column'])` for scalar testing but didn't show the full
  conversion the simulation loop actually needs.
- **Sample output cell shape** in `write_csv.py` mirrors the
  `0.0,0.0,3.0,cruise,,,` format from `instruction.md` so the agent can see
  how `None` columns serialize.
