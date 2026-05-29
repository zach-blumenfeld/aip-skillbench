# Distance metric choice

The task statement may specify any of:

- A formula (great-circle / haversine / Euclidean on a projected coordinate)
- An Earth radius (e.g., `3960.0` mi, `3958.8` mi, `6371` km)
- A pre-computed distance matrix in the data file (skip computation entirely)
- Output units (miles, kilometers, meters)

`scripts/routing_data.py` defaults to **great-circle miles, Earth radius
3960.0**. Confirm before relying on the default.

## Before building the distance matrix

1. **Formula.** Confirm the task asks for great-circle / haversine (same
   geometry, equal results to floating-point noise). If it specifies a
   planar / Euclidean / projected metric, do **not** use
   `great_circle_miles` — substitute a planar distance instead.
2. **Earth radius.** Pass `radius=` to `great_circle_miles` and
   `build_node_distances`. The bike-rebalance task family uses `3960.0`
   miles unless the task states otherwise.
3. **Output unit.** Match the unit the reported objective uses (miles vs
   kilometers vs meters). Multiply by `1609.344` to convert miles to
   meters; never mix units in the same model.
4. **Precomputed matrix.** If the task supplies a distance matrix, skip
   `build_node_distances` entirely and feed the supplied matrix into the
   optimization model directly.

## Common silent-failure modes

- **Wrong Earth radius.** Identical routes, objective off by a constant
  factor (e.g., `6371 / 3960 ≈ 1.61` if you swap miles for kilometers).
- **Euclidean on degrees.** Distortion grows with latitude; routes get
  wrong at high latitudes even though the math runs.
- **Mixed units.** Vehicle capacity in km, distance in miles — every
  feasibility check is silently wrong.
- **Rounding in the objective.** Rounding distances inside the
  optimization (e.g., to integer miles) changes the optimum. Keep the
  matrix in floats; round only for human-facing output.

## Decision recipe

```text
Does the task supply a distance matrix?
  yes -> use it; skip build_node_distances
  no  -> Does it say "great-circle" or "haversine"?
           yes -> great_circle_miles, with the task-supplied radius
           no  -> read the task carefully; substitute the right formula
```
