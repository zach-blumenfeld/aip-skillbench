---
name: csv-processing
description: Use this skill when reading sensor data from CSV files, writing simulation results to CSV, processing time-series data with pandas, or handling missing values in datasets. Covers pd.read_csv with explicit na_values, scalar pd.isna vs whole-column .notna() masks, time-window filtering, per-row iteration that bridges NaN to Python None, and writing DataFrames to CSV with index=False so empty cells match the task's expected output format.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Pandas patterns for the CSV side of the Adaptive Cruise Control task:
  reading sensor_data.csv (time / ego_speed / lead_speed / distance, with
  NaN in lead columns when no lead vehicle is present), filtering and
  iterating rows in the simulation loop, computing per-column statistics
  for the report, and writing simulation_results.csv with the exact column
  order and blank-cell behavior the task expects. Code templates live under
  assets/ — copy and adapt them into the task's own .py files
  (simulation.py, acc_system.py, an analysis script that builds
  acc_report.md).

trigger_when:
  - Reading a CSV with pandas, especially when blank / 'NA' / 'null' cells must parse as NaN.
  - Walking a time-series CSV row-by-row in a simulation loop (e.g., sensor_data.csv at dt=0.1s).
  - Deciding cruise vs follow mode based on whether lead_speed / distance is missing in the current row.
  - Filtering rows by time window or by "column not null" before computing metrics.
  - Building a results CSV incrementally from a list of per-step dicts (simulation_results.csv).
  - Computing summary statistics (mean / max / min / std) on a column for a report.

do_not_use_when:
  - The file format is YAML, JSON, TOML, or INI — see the sibling yaml-config skill for YAML.
  - The dataset is large enough that per-row Python iteration is too slow (millions of rows). The ACC task's 1501 rows are well within iterrows() range.

steps:
  - name: read-csv
    description: >
      Load a CSV with `pd.read_csv(path, na_values=['', 'NA', 'null'])` so blank
      and sentinel cells coerce to NaN. Inspect structure with `df.head()`,
      `df.columns.tolist()`, `len(df)`, and `df.isnull().sum()` before
      processing. Template at assets/read_csv.py.
    inputs:
      - name: path
        type: string
        description: Path to the CSV file (e.g., 'sensor_data.csv').
    outputs:
      - name: df
        type: object
        description: pandas DataFrame with NaN in cells that were blank, 'NA', or 'null'.
      - name: missing-by-column
        type: object
        nullable: true
        description: Optional NaN-count Series, useful as a sanity check before the simulation loop.

  - name: access-data
    description: >
      Select columns (`df['c']` or `df[['c1','c2']]`), filter rows by boolean
      mask (`df[(df['time'] >= t0) & (df['time'] < t1)]` — parenthesize each
      comparison), mask null/non-null with `df['col'].isna()` /
      `.notna()`, add computed columns (`df['diff'] = df['a'] - df['b']`), and
      compute summary stats (`mean / max / min / std`) per column. For per-row
      access inside the simulation loop, use `df.iterrows()` and test scalar
      NaN with `pd.isna(row['col'])` — `is None` and `== nan` both fail on
      NumPy NaN. When the downstream code branches on `lead_speed is None`
      (cruise vs follow mode), bridge NaN → None at the row boundary; see
      `iterate_sensor_rows` in assets/access_data.py.
    inputs:
      - name: df
        type: object
    outputs:
      - name: rows-or-stats
        type: object
        description: Filtered DataFrame, per-row tuples, or a stats dict — whichever the caller needs.

  - name: write-csv
    description: >
      Build results either as a dict of columns (`{'time': [...], ...}`) or by
      appending per-step dicts to a list and converting once at the end:
      `pd.DataFrame(records).to_csv(path, index=False)`. Use `index=False`
      always — the row index is not a task column. Use Python `None` (or
      `float('nan')`) for missing cells; both serialize to empty fields,
      matching expected rows like `0.0,0.0,3.0,cruise,,,` where the last
      three columns are blank in cruise mode. Column order in the output
      matches dict insertion order, so build each record with the exact key
      order the task specifies. Template at assets/write_csv.py.
    inputs:
      - name: records-or-columns
        type: object
        description: Either a dict-of-lists keyed by column, or a list of row-dicts.
      - name: path
        type: string
        description: Output CSV path (e.g., 'simulation_results.csv').
    outputs:
      - name: written-path
        type: string

scenarios:
  - need: Load sensor_data.csv and confirm the 1501 rows / 4 columns the task specifies, including NaN handling on lead_speed and distance.
    action: Apply `read-csv` with path='sensor_data.csv'. Print `len(df)`, `df.columns.tolist()`, and `df.isnull().sum()` to verify 1501 rows and to confirm lead_speed / distance have NaN where the lead vehicle is absent.
    outcome: Validated DataFrame ready for the simulation loop; missing-value count flags any unexpected data gaps before they propagate.

  - need: Inside simulation.py's per-timestep loop, decide cruise vs follow mode from sensor_data row N.
    action: "Iterate via `for _, row in df.iterrows():` and use `pd.isna(row['lead_speed'])` to test the scalar. Equivalently, call `iterate_sensor_rows(df)` from assets/access_data.py to get `(time, ego_speed, lead_speed_or_None, distance_or_None)` tuples and branch on `lead_speed is None` directly."
    outcome: Cruise mode triggered cleanly when the lead is absent; follow / emergency logic gets non-NaN floats.

  - need: Write simulation_results.csv with exactly 1501 rows and columns `time,ego_speed,acceleration_cmd,mode,distance_error,distance,ttc` — blank in the last three when mode == 'cruise'.
    action: Accumulate a list of dicts in the simulation loop, one per timestep, with the dict keys in the exact column order above. Use `None` for distance_error / distance / ttc in cruise rows. At the end, apply `write-csv` (`pd.DataFrame(records).to_csv('simulation_results.csv', index=False)`).
    outcome: CSV matches the expected format from instruction.md, including blank trailing cells in cruise rows.

  - need: Compute steady-state error / overshoot / minimum-distance metrics for acc_report.md.
    action: After loading simulation_results.csv via `read-csv`, filter the steady-state window (e.g., `df[df['time'] >= 60]`) and call `.mean()` / `.max()` / `.min()` on the relevant columns. For minimum distance during follow mode, filter `df[df['distance'].notna()]` first so cruise rows don't contaminate the result.
    outcome: Performance metrics ready to drop into the report's "Simulation results and performance metrics" section.

anti_patterns:
  - "Calling `pd.read_csv` without `na_values=['', 'NA', 'null']` — pandas's default coerces '' but leaves 'NA' / 'null' as string literals, silently breaking downstream NaN checks."
  - Using `value is None` or `value == float('nan')` to test a scalar cell from a row — both are False for NumPy NaN. Always use `pd.isna(value)`.
  - Forgetting `index=False` on `to_csv` — adds an unnamed integer column at position 0 that breaks the task's expected column layout.
  - Writing the string `'None'` (or `'NaN'`) into a record dict for a missing cell — serializes as those literal strings, not as blank. Use Python `None` or `float('nan')`.
  - Combining boolean masks without parentheses around each comparison (`df[df['a'] > 0 & df['b'] < 1]`) — Python's operator precedence binds `&` tighter than `<` / `>`, raising a confusing error or producing wrong rows. Wrap each side.
  - Using `dict.update` or column reassignment to "drop" a value to NaN when you actually wanted Python None — both end up as NaN in the DataFrame, which is fine for CSV but confuses downstream `is None` branches if you forgot to bridge.
  - Reordering record-dict keys per row — column order follows the first record's insertion order; later records with different key order can scramble the output.
```
