# Rebalancing MIP: formulation and modeling notes

Read this when you need to change `scripts/solve_rebalance.py` (a rule in the task differs from
the defaults below), when a solve does not reach `optimal`, or when you must explain the model.

## Data handling

- Station IDs are user-facing and need not be `0..n-1`. The script indexes stations
  `0..n-1` internally and writes original IDs to the report. Duplicate IDs are an error.
- Latitude/longitude are degrees and are range-checked (`[-90, 90]`, `[-180, 180]`);
  radians are used only inside the distance function.
- Distance = great-circle miles by the spherical law of cosines on colatitudes, with the
  Earth radius the task gives (default 3960.0), `cos_arc` clamped to `[-1, 1]`:
  `acos(sin(phi1) sin(phi2) cos(theta1 - theta2) + cos(phi1) cos(phi2)) * R`,
  `phi = (90 - lat) * pi/180`, `theta = lon * pi/180`.
  Do not substitute Euclidean-on-degrees, a haversine with another radius, meters,
  or rounded distances inside the objective.
- Depot appears twice: `depot_start` (only outgoing arcs) and `depot_end` (only incoming).
  The arc `depot_start -> depot_end` is omitted when every vehicle must visit a station,
  kept with `--allow-idle-vehicles`.

## Variables (vehicle v, station i)

| Variable | Type | Meaning |
| --- | --- | --- |
| `x[v,i,j]` | binary | vehicle v drives directly i -> j |
| `visit[v,i]` | expression | `sum_j x[v,i,j]` (no extra binary) |
| `s[v,i]` | integer | signed service: `> 0` pickup (vehicle load up, station down), `< 0` dropoff |
| `q[v,i,j]` | continuous `[0, C]` | bikes on board along arc i -> j, `q <= C x` |
| `dev[i]` | continuous `>= 0` | `abs(target - net)` linearised with two inequalities |

Report extraction: `bikes_picked_up = max(s, 0)`, `bikes_dropped_off = max(-s, 0)` — so a stop can
never both pick up and drop off. `start_load = sum_j q[v,START,j]`; `load_after_stop` is the
running sum; `end_load` is the last load.

## Constraints

| Rule | Constraint |
| --- | --- |
| Leave / return to depot once | `sum_j x[v,START,j] = 1`, `sum_i x[v,i,END] = 1` |
| Route continuity | `in(v,i) = out(v,i)` |
| Vehicle visits a station at most once | `out(v,i) <= 1` (per vehicle; other vehicles may also visit) |
| No split service (only if the task forbids it) | `sum_v out(v,i) <= 1` |
| Service only when visited | `-min(C, cap-init) * visit <= s[v,i] <= min(C, init) * visit` |
| Load conservation | `sum_h q[v,h,i] + s[v,i] = sum_j q[v,i,j]` |
| Vehicle capacity | `0 <= q <= C`, `q <= C x` (covers start, every stop, end) |
| Start empty (only with `--start-load zero`) | `sum_j q[v,START,j] = 0` |
| Station final inventory in `[0, cap]` | `init - cap <= sum_v s[v,i] <= init` |
| Unmet deviation | `net - target <= dev`, `target - net <= dev` |
| Objective | `sum dist * x + penalty_weight * sum dev` |

Never apply Python `abs()` to solver expressions. Big-M load propagation
(`load_j >= load_i + s_j - M(1 - x_ij)`) is valid but has a much weaker LP; the arc-flow form
above replaced it after big-M left a 9% gap at 300 s on the reference instance.

### Dominance restriction (`--dominance`, opt-in heuristic)

Default per-stop bounds are exact: pickups `<= min(C, init)`, dropoffs `<= min(C, cap - init)`.
`--dominance` adds `t_clip = clamp(target, init - cap, init)`. Each stop then serves only in the
target's direction, and the station's net change stays between 0 and `t_clip`. This is sometimes faster
(run-dependent: 11-80 s vs 35-48 s exact on the reference) but **not exact**. Moving a bike past the target, or the wrong way,
costs one unmet unit and can save one elsewhere. That ties on penalty but can allow a shorter
route. On the reference data with `--start-load zero`, the exact optimum is 8.820138 and
`--dominance` gives 8.827783; with free start load, both give 8.739464. Use it only as a fallback
when the exact model runs out of time, and keep the lower objective.

### Symmetry

Vehicles are identical, so the script orders them by route length
(`dist(v) >= dist(v+1)`). Remove this if vehicles ever differ (capacity, depot).

## Subtour elimination (`--subtour`)

Degree and continuity constraints still allow a depot path plus a separate station-only cycle.
Physical load does not rule that out (it rises and falls), so a dedicated mechanism is always
needed.

| Method | What it adds | Use |
| --- | --- | --- |
| `cut` (default) | Constraint handler: integer LP/candidate solutions get a cut for every station-only cycle; fractional LP solutions get generalised subtour cuts `arcs_into(Q) >= visit[v,k]` from a depot->k max-flow/min-cut | Strongest; proves optimality in well under the 300 s default on the 15-station reference |
| `mtz` | `order[v,i] - order[v,j] + n x[v,i,j] <= n - 1`, `order in [1, n]` | Compact `O(K n^2)`, weak LP; fallback if the handler misbehaves |
| `flow` | Artificial single-commodity flow from depot, one unit per visited station, `f <= n x` | Static, stronger than MTZ in theory; slower here. Never reuse truck load as this flow |

Static enumeration of all DFJ subsets is exponential: fine only for roughly 15 stations or fewer,
and only as a debugging baseline. Re-solving from scratch after each round of cuts (the iterative
variant) is simpler but timed out here; the handler gives true lazy cuts instead. Multi-commodity
flow is very strong but too large for practical use.

Measured on the reference data (2 vehicles, 15 stations; dominance on): `cut` optimal 8.739464 in 11 s;
`mtz` 8.752 with 12% gap at 60 s; `flow` 9.046 with 19% gap at 60 s.

## Solver settings

- `pyscipopt` is required; do not install another solver.
- Randomisation seeds fixed to 0 and `parallel/maxnthreads = 1` for reproducibility (set via
  try/except because parameter names vary across versions).
- `limits/time` = `--time-limit` (default 300 s), `limits/gap` = `--gap` (default 0.0; the
  source template used 0.01, but a 1% gap can be the difference from a reference objective).
- At least one incumbent is required before extraction; if none, the script exits with an error.
- The report is recomputed from the extracted routes (distance from coordinates, unmet from
  station totals), never copied from the solver objective. The script also checks that the
  selected arcs form a single depot-to-depot path with no leftover cycle.
