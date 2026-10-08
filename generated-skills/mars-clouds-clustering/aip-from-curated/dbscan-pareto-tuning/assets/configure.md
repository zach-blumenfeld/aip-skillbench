Build the run config for `{meta.name}`: a DBSCAN hyperparameter sweep that clusters
crowd (citizen-science) point marks per image, matches cluster centroids to expert
marks, and keeps the Pareto frontier of (F1 ↑, delta ↓).

Task instructions:

{task_instructions}

If the state already holds `config_problems`, `profile`, or `result_notes` from an earlier
pass, this is a retry: fix exactly what they report and keep the rest.

Defaults (`assets/default_config.json`):

{assets[default_config]}

Produce `config`: a JSON object holding ONLY the keys whose value must differ from the
defaults (the scripts merge it over the defaults). Map every number and rule the task
states onto a key; where the task is silent, keep the default.

- Paths: `citsci_csv` (crowd marks), `expert_csv` (ground truth), `output_csv` (Pareto
  CSV; use the exact path the task names), optional `all_results_csv` (full grid, for
  debugging; leave "" unless useful).
- Columns: `frame_col` is the per-image key. Use `frame_file` for the Mars cloud-arch
  CSVs: `file_rad`/`subject_ids` cover the whole 4-frame subject, so grouping on them
  mixes four images. `x_col`/`y_col` are the pixel coordinates.
- Row filters: `citsci_filter` / `expert_filter` map column -> allowed values (e.g.
  `{{"tool_label": ["Arch peak marker"]}}`). Add them only if the task asks, or if the
  profile shows rows that are not the marks being clustered. In the Mars expert file
  `workflow_name` mixes `demonstration` and `arch_peak_default`. Both are the expert's
  arch-peak marks, so do not filter on it unless the task says to.
- Grids: `min_samples`, `epsilon`, `shape_weight` take a list or
  `{{"start", "stop", "step"}}`, and `stop` is INCLUSIVE ("4 to 24 step 2" -> 4..24).
- Distance: weighted Minkowski on scaled axes, d = (|sx·Δx|^p + |sy·Δy|^p)^(1/p), with
  `x_scale`/`y_scale` given as arithmetic expressions in `w` (the shape weight) and
  `minkowski_p` (2 = Euclidean, 1 = Manhattan). Default `w` / `2 - w`, so w > 1
  stretches x and treats points as close when they lie along the same horizontal band.
  Copy the task's formula exactly.
- Matching: `match_max_distance` (pixels; plain Euclidean, unweighted), `match_mode`
  (`assign_then_filter`, the default for "Hungarian, matches within X px": solve on the
  raw cost matrix, then drop pairs over the limit; `mask_then_assign` only when the task
  says over-limit pairs may not be assigned at all).
- Scoring: `frames` (`intersection` = images with both crowd and expert marks;
  `expert` = every expert image, a missing crowd image scores F1 = 0; `union`),
  `f1_aggregation` (`per_image_mean` | `global` TP/FP/FN), `delta_aggregation`
  (`per_image_mean` over images with at least one match | `global_pairs`),
  `centroid` (`mean` | `median`).
- Frontier: `f1_min` with `f1_min_inclusive` (false means strictly greater than),
  `pareto_distinct` (true means paretoset's default: one row per identical (F1, delta)
  pair; false keeps every tied parameter combination), `output_columns`, `round_decimals`,
  `sort_by`, `sort_ascending`.

Load `references/method.md` if a task phrase does not obviously map to a key.
Return JSON: `{{"config": {{...}}}}`.
