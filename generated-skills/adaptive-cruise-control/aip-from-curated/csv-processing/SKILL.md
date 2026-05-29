---
name: csv-processing
description: Use this skill when reading sensor data from CSV files, writing simulation results to CSV, processing time-series data with pandas, or handling missing values in datasets.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Pandas idioms for the simulation CSV I/O loop — read a time-indexed sensor
  CSV with NA detection, navigate rows during a fixed-timestep simulation,
  accumulate per-timestep result records, and write the output CSV with the
  exact column order the task spec requires and explicit empty-cell handling
  for fields that don't apply at a given step.

trigger_when:
  - Reading sensor_data.csv or any time-indexed sensor CSV with pandas.
  - Writing simulation_results.csv or building an output CSV from a per-timestep loop.
  - A CSV column may contain missing readings (NA, '', 'null') that must propagate as NaN.
  - Needing a pandas idiom for filtering rows, iterating, or computing summary statistics.

do_not_use_when:
  - The data is not tabular (use a JSON or YAML skill instead — see the yaml-config skill for vehicle_params.yaml).
  - The transformation is a single shell pipeline (awk / cut / csvkit) with no per-row logic.

steps:
  - name: read-csv
    description: >
      Load the CSV with pd.read_csv, passing na_values=['', 'NA', 'null'] so
      missing sensor readings parse as NaN rather than empty strings.
      See references/pandas-patterns.md § Reading.
    outputs:
      - { name: df, type: object, description: pandas DataFrame holding the raw rows. }

  - name: inspect-schema
    description: >
      Print df.head(), df.columns.tolist(), and len(df) before downstream code
      depends on the structure. Confirms row count (e.g., 1501 for the 150-s,
      0.1-s ACC trace) and column names match the task spec.
    inputs:
      - { name: df, type: object }

  - name: handle-missing
    description: >
      Inside the simulation loop, use pd.isna(row[col]) to detect missing
      readings per row. For the ACC task, NaN in lead_speed or distance means
      no lead vehicle is detected — pass None into the ACC compute() so it
      selects 'cruise' mode. Use df[col].notna() when filtering whole columns.
    inputs:
      - { name: df, type: object }
    outputs:
      - { name: lead_present, type: boolean, description: Whether a lead vehicle reading is non-NaN at this timestep. }

  - name: access-data
    description: >
      Select columns (df['col'] / df[['a','b']]), filter rows by predicate
      (df[df['time'] >= 30]), or index by position (df.iloc[i]) inside the
      fixed-timestep simulation loop. See references/pandas-patterns.md § Accessing.
    inputs:
      - { name: df, type: object }

  - name: build-results
    description: >
      Accumulate per-timestep dicts in a Python list during the simulation
      loop. Construct each dict with keys in the EXACT column order the spec
      requires (DataFrame preserves insertion order). Use None for fields
      that don't apply at this step (e.g., distance_error / distance / ttc
      while in 'cruise' mode) — None renders as an empty cell on write.
    outputs:
      - { name: results_list, type: "list[object]", description: One dict per simulation timestep. }

  - name: write-csv
    description: >
      Convert results_list to a DataFrame and write with index=False so the
      output has no extra unnamed index column. The dict insertion order from
      build-results is preserved as the CSV column order.
    inputs:
      - { name: results_list, type: "list[object]" }
    outputs:
      - { name: csv_path, type: string, description: Path to the written output CSV. }

  - name: summary-stats
    description: >
      Optional. Compute df[col].mean() / .max() / .min() / .std() for the
      performance-metrics section of acc_report.md (speed steady-state error,
      overshoot, minimum distance, etc.). See references/pandas-patterns.md § Common Operations.
    inputs:
      - { name: df, type: object }
    outputs:
      - { name: metrics, type: object, nullable: true }

scenarios:
  - need: Read sensor_data.csv (1501 rows over t = 0–150 s, columns time / ego_speed / lead_speed / distance) where lead_speed and distance may be NaN when no lead vehicle is in view.
    action: |
      pd.read_csv('sensor_data.csv', na_values=['', 'NA', 'null']);
      assert len(df) == 1501 and df.columns.tolist() == ['time','ego_speed','lead_speed','distance'].
    outcome: DataFrame is ready for per-row iteration; absent lead-vehicle readings are NaN, not empty strings.

  - need: At simulation timestep i, decide whether a lead vehicle is present and dispatch to ACC.
    context: row = df.iloc[i] inside the fixed-0.1-s simulation loop.
    action: |
      lead_speed = None if pd.isna(row['lead_speed']) else float(row['lead_speed']);
      distance = None if pd.isna(row['distance']) else float(row['distance']);
      acc.compute(ego_speed, lead_speed, distance, dt).
    outcome: ACC.compute() sees None for missing lead readings and routes to 'cruise' mode per the task spec.

  - need: Write simulation_results.csv with the exact columns time, ego_speed, acceleration_cmd, mode, distance_error, distance, ttc — with empty cells in distance_error / distance / ttc whenever the row is 'cruise'.
    action: |
      Inside the loop append {'time': t, 'ego_speed': v, 'acceleration_cmd': a, 'mode': m,
      'distance_error': None, 'distance': None, 'ttc': None} during 'cruise', or populated
      values during 'follow' / 'emergency'; then pd.DataFrame(results).to_csv('simulation_results.csv', index=False).
    outcome: Output CSV matches the spec's column order; None values render as empty cells.

  - need: Compute final-100-row mean of ego_speed for the steady-state-error metric in acc_report.md.
    action: results_df['ego_speed'].iloc[-100:].mean() — or filter df[df['time'] >= 140]['ego_speed'].mean().
    outcome: Scalar metric value ready for the report.

anti_patterns:
  - Calling pd.read_csv without na_values — empty strings remain '' instead of NaN, so pd.isna() checks silently miss them.
  - Writing the output with df.to_csv(path) without index=False — adds an unnamed leading index column and breaks the spec's column order.
  - Filling missing distance / distance_error / ttc with 0 or -1 during 'cruise' mode — the spec expects empty cells; sentinel values corrupt downstream metrics.
  - Building results into a DataFrame via repeated df.loc[i] = ... inside the loop — quadratic-time and error-prone; accumulate dicts in a list and convert once at the end.
  - Relying on the column order from a df[['a','b']] selection without matching that order when constructing the output dict — write the dict in the spec's exact order to stay robust.
  - Using df.iterrows() inside the inner 0.1-s simulation loop when df.iloc[i] is sufficient — iterrows is materially slower for 1501-step traces.
```
