# Output specification — reference

For each command file (e.g. `commands/001.txt`) the skill writes a folder
`/root/results/001/` containing exactly the files below. Schemas are strict —
extra keys or different row counts must not appear.

## Directory layout

```
/root/results/<id>/
├── metrics_3d.json
├── tuning_results.json
├── planned_trajectory.npy
├── actual_trajectory.npy
└── plots/
    ├── desired_vs_actual.png
    ├── errors.png
    └── cumulative_errors.png
```

## `metrics_3d.json`

Exactly these five keys, in this order, with these types:

```json
{
  "mode": "takeoff",          // one of: "takeoff", "hover", "land", "fly"
  "RiseTime": 1.23,           // seconds
  "SettlingTime": 2.45,       // seconds
  "Overshoot_pct": 3.1,       // percent, >= 0
  "SteadyStateError": 0.01    // meters
}
```

Computed with `settling_threshold = 0.02` (2% band of step size).

The axis used:
- `takeoff`, `hover`, `land` → z
- `fly` → the axis with the largest commanded displacement

## `tuning_results.json`

Exactly these six keys; each value a length-3 list of floats `[x, y, z]`:

```json
{
  "kp_pos": [4.0, 4.0, 6.0],
  "ki_pos": [0.4, 0.4, 1.0],
  "kd_pos": [3.0, 3.0, 4.0],
  "kp_att": [120.0, 120.0, 40.0],
  "ki_att": [0.0, 0.0, 0.0],
  "kd_att": [20.0, 20.0, 10.0]
}
```

## `planned_trajectory.npy` and `actual_trajectory.npy`

Float ndarray, shape `(15, max_iter)`. Row layout:

| Rows  | Quantity            | Units   |
|-------|---------------------|---------|
| 0:3   | position [x, y, z]  | m       |
| 3:6   | velocity [vx,vy,vz] | m/s     |
| 6:9   | orientation [φ,θ,ψ] | rad     |
| 9:12  | angular vel [p,q,r] | rad/s   |
| 12:15 | acceleration [a]    | m/s²    |

`max_iter = round((t_cmd + settle_pad) / dt) + 1` where
`settle_pad = max(3.0, 0.5·t_cmd)`. Default `dt = 0.01` s.

The planned matrix sets orientation/angular-velocity rows to 0; those are
controller-derived, not part of the planner's job.

## Plots

Three PNGs under `plots/`. Fixed names:

- `desired_vs_actual.png` — 3 stacked subplots, position desired vs actual on
  x, y, z.
- `errors.png` — signed per-axis errors plus Euclidean error, with horizontal
  `±0.05 m` spec lines.
- `cumulative_errors.png` — `∫|error|·dt` per axis and Euclidean.

## Success rubric

A command counts as successfully executed iff **all four** hold:

1. `SteadyStateError < 0.05` m
2. `Overshoot_pct < 5`
3. Planned trajectory acceleration within physical limits at every timestep
4. Per-timestep Euclidean position error < 0.05 m at every timestep

`scripts/verify_specs.py` rechecks each constraint after the artifacts are
written.
