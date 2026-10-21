# Bike-rebalancing MIP: what the scripts build and how to adapt it

Read this only when a rule in the task statement is not covered by the three
`read-rules` questions, when a script fails, or when you must change the model.
Everything below is already implemented in `scripts/rebalance_core.py`.

## Data handling (geospatial)

- Parse `data.json` with a JSON parser. Map station ids to internal indices
  (`id_to_idx`) for the model and map back for the report. Never assume ids are
  `0..n-1`; keep each id's original JSON value (an int stays an int) in the report.
- Reject duplicate station ids and coordinates outside lat [-90, 90] / lon [-180, 180].
  Latitude and longitude are degrees; convert to radians only inside the distance function.
- Great-circle miles with the task's Earth radius (3960.0 here), spherical law of
  cosines on colatitudes, `cos_arc` clamped to [-1, 1] before `acos`:
  `phi = (90 - lat) * pi/180`, `theta = lon * pi/180`,
  `cos_arc = sin(phi1) sin(phi2) cos(theta1 - theta2) + cos(phi1) cos(phi2)`,
  `d = acos(cos_arc) * radius`.
- Do not mix: Euclidean distance on degrees; haversine with another radius; miles and
  meters; rounded distances inside the objective.
- Depot is split into two labels, `depot_start` (arcs out) and `depot_end` (arcs in).
  The `depot_start -> depot_end` arc exists only when vehicles may stay home.
- Report distance is recomputed from the route coordinates, never copied from the
  solver objective; compare floats with a tolerance, not string equality.

## Sets and variables

| Symbol | Meaning | Type |
| --- | --- | --- |
| `x[v,i,j]` | vehicle `v` drives `i -> j` (from `[START, stations]` to `[stations, END]`) | binary |
| `svc[v,i]` | signed bikes moved at the stop: `> 0` pick up, `< 0` drop off | integer in `[-Q, Q]` |
| `flow[v,i,j]` | bikes on board while driving `i -> j` | continuous `[0, Q]` |
| `start_load[v]` | bikes on board leaving the depot | integer `[0, Q]`, or fixed 0 |
| `order[v,i]` | MTZ position of station `i` in `v`'s route | continuous `[1, n]` |
| `unmet[i]` | `|target_i - net_i|` | continuous `>= 0` |

One signed service variable per stop makes "do not both pick up and drop off at one
stop" automatic: `bikes_picked_up = max(svc, 0)`, `bikes_dropped_off = max(-svc, 0)`.

## Rule -> constraint

| Rule | Constraint |
| --- | --- |
| each vehicle leaves and returns to depot | `sum_j x[v,START,j] = 1`, `sum_i x[v,i,END] = 1` |
| route continuity | `in(v,i) = out(v,i)` per station |
| a vehicle visits a station at most once | `out(v,i) <= 1` (per vehicle; other vehicles may also visit — split service) |
| vehicle must visit some station | omit the `START->END` arc |
| only one vehicle per station (only if the statement says so) | `sum_v out(v,i) <= 1` |
| service only at a visited station | `-Q*out(v,i) <= svc[v,i] <= Q*out(v,i)` |
| load bounds 0..Q at every point | `flow[v,i,j] <= Q*x[v,i,j]`, `flow >= 0` |
| load update `load_after = previous + up - down` | `out_flow(v,i) - in_flow(v,i) = svc[v,i]`; `out_flow(v,START) = start_load[v]` |
| final inventory in `[0, capacity]` | `initial - capacity <= sum_v svc[v,i] <= initial` |
| unmet = abs(target - net) | `net - target <= unmet`, `target - net <= unmet` (never Python `abs()` on solver expressions) |
| objective | `sum dist*x + penalty_weight * sum unmet` |

Station inventory is only constrained at the end of the night (no visit timing), so one
vehicle may drop bikes at a station another vehicle picks up from.

## Subtour elimination

Degree and continuity constraints allow a depot path plus a detached station cycle, and
physical load cannot rule this out because pickups and drops let load rise and fall.
The scripts use:

1. **Lifted MTZ** (Desrochers–Laporte) `order_i - order_j + n x_ij + (n-2) x_ji <= n-1`
   plus `x_ij + x_ji <= 1`. MTZ alone guarantees connected routes but its LP bound is weak:
   on the 15-station, 2-vehicle instance it left a 6–8% gap after 300 s.
2. **Exact generalized subtour cuts** separated on every LP: for each vehicle and station
   `k`, max-flow from `START` to `k` over `x`; if below `y_k = out(v,k)`, add
   `x_v(into S) >= y_k` for the min-cut sink side `S`. This proves optimality in ~10 s
   on the same instance. The cuts only tighten the bound; MTZ keeps correctness.

Alternatives, if you rebuild the model: single-commodity connectivity flow (stronger than
MTZ, `O(Kn^2)` continuous variables; never reuse the truck load as that flow); static DFJ
enumeration only for tiny `n` (exponential, < ~15 stations); iterative DFJ (solve, find
cycles without `START` in the incumbent, add `x(S) <= |S| - 1`, call `freeTransform()`,
re-solve) when callbacks are inconvenient. Multi-commodity flow is too heavy for most tasks.

## Solver settings

- `pyscipopt` ships in the container; do not install another solver.
- `hideOutput()`, `limits/time`, single thread, fixed random seeds for repeatability.
- Identical vehicles: `first_station(v) <= first_station(v+1)` cuts symmetric branches.
- The pyscipopt LP is slow (~2,500 simplex iterations/s); at 20 stations x 3 vehicles SCIP
  processes only a handful of nodes per minute and its own incumbents stay poor. So
  `RouteSearch` (iterated local search: relocate, swap, 2-opt, add/remove/split visits,
  random-relocation kicks) runs first. It scores routes with greedy services: for a fixed
  start load, picking or dropping as much as is useful at each stop is optimal on one route
  (one extra bike on board changes later moves by at most one), and every allowed start
  load is tried. `exact_plan` then fixes the best routes in the MIP to get exact services.
  On the 15-station instance search alone reaches the optimum in ~3 s; on harder variants it
  beat 120 s of plain SCIP by up to 15%.
- A trivial plan (each vehicle visits its nearest station, moves nothing) is also added as a
  start solution, so an incumbent always exists. Require `getNSols() > 0` before reading values.
- Read binaries with `> 0.5`, integers with `round()`. Reconstruct each route by following
  selected arcs from `START`; fail on a disconnected route or a repeated station.

## Generic rule-translation patterns (for rules this task does not have)

List entities, choose variables (binary for choices, integer for unit counts, continuous
for time/flow/cost), map each rule to conservation / capacity / linking (`q <= U*use`,
tightest `U`) / assignment / sequence (big-M from real bounds) / compatibility
(`x_a + x_b <= 1`) / soft penalty with slack, add the objective last with named
components, then recompute everything from the output. Examples: optional vehicle
`sum_j x[v,START,j] = use[v]` and a fixed cost `c*use[v]`; time windows
`earliest <= arrival <= latest` with `arrival_j >= arrival_i + service_i + travel_ij - M(1-x_ij)`;
route duration `sum travel*x <= max_duration`; precedence `start_b >= finish_a`;
demand that must be met `served >= demand`, or that may go unmet `served + unmet >= demand`.
Assignment: exactly one `sum_j x_ij = 1` or at most one `<= 1`; per-option capacity
`sum_i w_i x_ij <= cap_j`; open before assign `assign_ij <= open_j`; mutually exclusive
modes `sum_m mode_im <= 1`; inventory over periods `inv[t+1] = inv[t] + in - out`,
`out[t] <= inv[t]`, `inv <= capacity`. Station-indexed visit binaries, if a model needs
them repeatedly: `visit[v,i] = sum_j x[v,i,j]`.
