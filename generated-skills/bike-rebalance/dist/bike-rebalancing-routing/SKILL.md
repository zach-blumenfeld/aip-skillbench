---
name: bike-rebalancing-routing
description: Solve nightly bike-share station rebalancing as a vehicle-routing MIP with SCIP (PySCIPOpt). Plans routes for a fleet of capacity-limited vehicles from one depot and picks up / drops off bikes at stations to meet signed net_rebalancing_target values. Minimizes great-circle travel miles plus penalty_weight times unmet bikes, then writes and independently validates report.json (summary, per-vehicle routes/stops/loads, per-station totals). Use for data.json-driven pickup/dropoff rebalancing, 1-PDTSP/VRP with station inventory limits, or validating such a routing report.
compatibility: Python >= 3.10; pyscipopt (tested 6.1.0) for scripts/solve_rebalance.py; scripts/validate_report.py is standard-library only. No other packages or tools.
---

# Bike Rebalancing Routing

## Trigger When

1. A task gives `data.json` with `vehicle_count`, `vehicle_capacity`, `penalty_weight`, a `depot`,
   and `stations` carrying `net_rebalancing_target`, `initial_bikes`, `station_capacity`, and
   asks for vehicle routes plus pickup/dropoff quantities in a `report.json`.
2. Any pickup-and-delivery or rebalancing routing problem: depot start/end, vehicle load limits,
   station inventory limits, soft targets penalized per unit, and travel distance from lat/lon.
3. Checking an existing routing report for rule violations, or recomputing its distance and objective.

## Purpose

Takes the rules from the task statement, builds a SCIP routing MIP, and writes the report. The
model uses arc variables per vehicle, signed integer service, arc-flow vehicle load, station
final-inventory bounds, and a linearized absolute deviation penalty. Subtours are cut lazily by
branch-and-cut. A separate validator then re-checks every rule from the report alone. The skill
adds things an agent would not get right unaided: the exact great-circle formula, the reporting
conventions, which rules are per vehicle and which are global, and a formulation that reaches
proven optimality in seconds. A plain MTZ/big-M model stalls at a 9-12% gap.

## Workflow

Run every command from this skill's folder. In the container, the input is `/root/data.json`.
Write `/root/report.json` unless the task names another output path.

- [ ] 1. Check the environment
- [ ] 2. Decide the task-rule flags (decision)
- [ ] 3. Solve (script)
- [ ] 4. Branch on solver status
- [ ] 5. Validate (script)
- [ ] 6. Report back (client task)

### 1. Check the environment (execution)

```bash
python -c "import sys, pyscipopt; assert sys.version_info >= (3, 10); print(pyscipopt.__version__)"
```

If this fails, name everything missing (Python >= 3.10, `pyscipopt`). Do not swap in another
solver or a greedy heuristic. The task container ships `pyscipopt==6.1.0`.

### 2. Decide the task-rule flags (decision)

Input: the task statement (instruction text) and the `data.json` keys. Answer all of these in one pass.

```yaml
start_load_policy:
  type: choice
  instructions: May a vehicle leave the depot already carrying bikes?
  criteria:
    free: The statement only bounds start_load (e.g. ">= 0 and <= vehicle_capacity") or says nothing that fixes it. This is the default.
    zero: The statement says vehicles start empty, start_load must be 0, or the depot has no bikes.
every_vehicle_must_visit:
  type: noul
  instructions: Must every vehicle visit at least one station (no depot-only routes)?
  criteria:
    true: The statement says a vehicle must visit some stations / cannot just stay at the depot, or says all vehicles are used.
    false: Vehicles are explicitly optional or may stay at the depot.
split_service_allowed:
  type: noul
  instructions: May two different vehicles both serve the same station?
  criteria:
    true: The only visit rule is per vehicle ("a vehicle can visit a station no more than once"), or the statement is silent.
    false: The statement says each station is visited by at most one vehicle in total.
```

Costly mistakes. Leaning toward `zero` when the text only bounds start_load forces a worse
objective (8.82 vs 8.74 on the reference data). Reconsider any close call that leans `zero`.
Wrongly answering `split_service_allowed = false` is costly too: targets larger than
`vehicle_capacity` can then never be met (11.70 vs 8.74 on the reference data). Reconsider any
close call that leans false.

Also read from the statement: the Earth radius (default `3960.0`) → `--radius`. If the distance
metric is not great-circle miles, edit `great_circle_miles` in both scripts before solving.

Map answers to flags: `zero` → `--start-load zero`; `every_vehicle_must_visit = false` →
`--allow-idle-vehicles`; `split_service_allowed = false` → `--no-split-service`.

### 3. Solve (execution)

```bash
python scripts/solve_rebalance.py --data /root/data.json --out /root/report.json \
  [--start-load zero] [--allow-idle-vehicles] [--no-split-service] [--radius R] \
  [--time-limit 300]
```

The script writes the report and prints JSON with `status`, `gap`, `solve_seconds`, `optimal`,
and `summary`. Defaults: `--subtour cut`, `--gap 0.0`, exact model. Read
[references/model.md](references/model.md) before changing the model, or to explain the formulation.

### 4. Branch on solver status

- `optimal: true` → go to step 5.
- `status: timelimit` with a report written → the report is a feasible incumbent. If time
  allows, rerun with a larger `--time-limit` (double it) and keep whichever report has the lower
  `summary.objective`. If the longer run also stops at the time limit, try one run with
  `--dominance`, writing to a scratch path. It is a smaller, non-exact search space that can close
  faster (see references/model.md). Keep the lowest objective. If there is no time for reruns,
  keep the incumbent and state the gap.
- `ERROR: SCIP found no feasible solution` with status `timelimit` → rerun with a larger
  `--time-limit`. With status `infeasible` → recheck the step-2 answers. For example,
  `--no-split-service` with more vehicles than stations is infeasible when every vehicle must
  visit.
- If `--subtour cut` itself errors (constraint-handler exception), rerun with `--subtour mtz`
  and a longer time limit.

### 5. Validate (execution)

```bash
python scripts/validate_report.py --data /root/data.json --report /root/report.json \
  [--radius R] [--allow-idle-vehicles] [--no-split-service]
```

Pass the same rule flags as step 3. `VALID ...` with exit 0 means every rule in the task
holds and the summary arithmetic matches a recomputation from coordinates. On `INVALID`, read
the listed violations. Fix the cause (usually a flag mismatch, or a hand edit to the report),
re-solve, and validate again. Never hand-patch numbers to pass.

### 6. Report back (client task)

Tell the user the report path, `objective`, `travel_distance_miles`,
`total_unmet_rebalancing_amount` and its penalty, the solver status/gap, and the flags chosen in
step 2 with a one-line reason each. Name any stations whose target could not be met and why
(e.g. target exceeds `initial_bikes`, or exceeds free docks).

## Report format (what the script writes)

```json
{"summary": {"objective": 0.0, "travel_distance_miles": 0.0,
             "unmet_rebalancing_penalty": 0.0, "total_unmet_rebalancing_amount": 0.0},
 "vehicles": [{"vehicle_id": 1, "start_load": 0.0,
               "route": ["depot_start", 393, "depot_end"],
               "stops": [{"station_id": 393, "bikes_picked_up": 4.0,
                          "bikes_dropped_off": 0.0, "load_after_stop": 4.0}],
               "end_load": 4.0}],
 "stations": [{"station_id": 393, "net_rebalancing_target": 4.0, "total_bikes_picked_up": 4.0,
               "total_bikes_dropped_off": 0.0, "net_bike_change": 4.0,
               "unmet_rebalancing_amount": 0.0}]}
```

One vehicle object per vehicle (`vehicle_id` 1..`vehicle_count`). One station object per
data.json station, in data order, including untouched ones. Quantities are floats with integer values.

## Gotchas

- Sign convention: positive target = pick up from the station (vehicle load +, station −).
  `net_bike_change = picked − dropped`, and `unmet = |target − net_bike_change|`.
- Station rules apply to the final inventory only: `initial − picked + dropped` must lie in
  `[0, station_capacity]`. A target above `initial_bikes` (or a dropoff beyond free docks) is
  partly unmeetable. The model accepts the penalty and does not fail.
- "Visit at most once" is per vehicle. A target bigger than `vehicle_capacity` (e.g. −34 with
  capacity 25) needs two vehicles at that station, so do not add a global single-visit rule
  unless the task says so.
- `end_load` may be positive: bikes may return to the depot. A start load is allowed unless
  step 2 said `zero`.
- Route IDs are the original station IDs, never internal indices. The route starts with
  `"depot_start"`, ends with `"depot_end"`, and has stops in the same order as its stations.
- Use the exact distance formula and radius, unrounded. `travel_distance_miles` must be
  recomputable from the routes, and the script recomputes it rather than copying the solver objective.
- Physical load cannot replace subtour elimination, and MTZ/big-M alone leave large gaps.
  Keep the default `--subtour cut`.
