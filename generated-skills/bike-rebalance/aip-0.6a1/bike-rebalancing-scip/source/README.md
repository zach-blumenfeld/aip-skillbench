# Source and compilation notes: bike-rebalancing-scip

## Provenance

Compiled on 2026-10-20 from four curated Agent Skills, copied verbatim into this folder:

| Folder | What it contributed |
| --- | --- |
| `geospatial-routing-data/SKILL.md` | data.json parsing, id <-> index mapping, coordinate checks, great-circle formula (radius 3960, clamped `acos`), `depot_start`/`depot_end` labels, route reconstruction and route checks |
| `logistics-rules-to-optimization/SKILL.md` | rule -> variable/constraint translation, signed pickup/drop-off service, station inventory bounds, absolute-deviation unmet slack, global vs per-vehicle visit rules |
| `routing-subtour-elimination/SKILL.md` | MTZ, connectivity flow, DFJ and iterative cuts, method choice, "do not use load as SEC", route extraction that fails fast |
| `scip-opt/SKILL.md` | PySCIPOpt workflow, time limits, incumbent check, reproducibility parameters, extraction thresholds, independent validation |

Also used: the task statement (`instruction.md`: rules list, report format, Earth radius
3960.0), the container Dockerfile (python:3.12-slim, `pyscipopt==6.1.0`, data at
`/root/data.json`), and the real `data.json` (15 stations, 2 vehicles, capacity 25,
penalty 0.5) for functional testing.

## Intent

One skill that takes a rebalancing data.json and produces a verified, optimal (or
best-found) report.json without the agent writing a model by hand.

## Component-kind choices

| Step | Kind | Why |
| --- | --- | --- |
| `inspect-instance` | execution | Parsing and data validation are deterministic; it fails fast on bad data and gives the decision a compact summary. |
| `read-rules` | decision (3 nouls) | Three modelling switches depend on reading the statement's wording: may vehicles leave loaded (the statement only bounds `start_load`, and that changes the optimum: 8.7395 vs 8.8201 on the real data), must every vehicle visit a station, and are stations exclusive to one vehicle. The answer space is fixed, so these are typed decisions, not prose. |
| `solve` | execution | Model building, route search, solving, and report assembly are pure computation. |
| `by-solve-status` | router | An unproven incumbent is worth a longer, warm-started second attempt; a proven optimum is not. |
| `polish` | execution | Same computation with a warm start and a longer limit; never makes the report worse. |
| `verify` | execution | Every task rule is a fixed, checkable formula; the checker recomputes from data.json and exits non-zero with every violation. |
| `end` | end | Report path plus the verified summary numbers. |

No `client_task`: nothing in the workflow needs generated text. `references/model.md`
holds the math and extension patterns for when a statement has a rule the switches do not
cover; the `solve` step description says when to read it.

### Model choices that differ from the sources (tested, deliberate)

- **Arc-load flow instead of big-M node loads.** The source's load-transition pattern
  (`load_j - load_i - change_j` within `+-M(1 - x_ij)`) plus plain MTZ left a 6% gap after
  300 s on the real data. Carrying load on arcs (`flow <= Q x`) with conservation at stops
  is equivalent and tighter.
- **Lifted MTZ plus exact generalized subtour cuts** (max-flow separation in a PySCIPOpt
  `Sepa`). Together they prove the real instance optimal in about 10 s of SCIP time. MTZ
  stays in the model, so connectivity never depends on the separator.
- **Route local search before SCIP.** The pyscipopt LP manages about 2,500 iterations/s. On
  perturbed 15–20 station, 2–3 vehicle instances SCIP alone stalled with 5–31% gaps at
  120 s and poor incumbents. Seeding it with an iterated local search fixed that
  (for example 7.33 vs 8.63 and 16.06 vs 17.59).
- **Free start load is a decision, not a default.** The sources and the task example show
  `start_load: 0.0` but the rules only bound it to `[0, vehicle_capacity]`.
- **Vehicle-symmetry cut** (first station index non-decreasing across identical vehicles).
  Warm starts and fixed-route solves sort vehicles to match it.

## Deliberate-drop log

| Source item | Decision | Rationale |
| --- | --- | --- |
| scip-opt "When To Use" list and solver marketing paragraph | dropped | Background; the procedure always uses SCIP. |
| scip-opt `limits/gap = 0.01` in the template | dropped | The skill proves optimality (gap 0) when time allows; a 1% gap would hand back a worse report on instances that solve in seconds. |
| scip-opt minimal template (generic items/amount/dev), binary-activation and assignment snippets | condensed | The task model is fully implemented in `scripts/rebalance_core.py`; generic patterns are kept as one-liners in `references/model.md`. |
| logistics big-M load-transition snippet | replaced | See arc-load flow above; the source's warning to pick `M` from real bounds is moot without big-M loads. |
| logistics time-window, precedence, route-duration, fixed-cost, assignment rows | kept as one-liners in `references/model.md` | Not rules of this task; kept so the agent can extend the model if a statement adds them. |
| routing-subtour pros/cons prose for each method | condensed | Kept as the method-choice paragraph in `references/model.md`; the scripts implement the chosen method. |
| routing-subtour iterative DFJ loop code | condensed | Replaced by exact separation inside SCIP; the loop is described (solve, find cycles without START, add `x(S) <= |S|-1`, `freeTransform()`, re-solve) in `references/model.md`. |
| geospatial code snippets (`parse_location`, `parse_report_route`, `route_distance_*`, `assert_close`) | moved into scripts | Implemented in `rebalance_core.load_instance`, `plan_from_report`, and `verify.py`. |
| geospatial `distances` over `START->END` when direct depot travel is allowed | kept in code | The arc exists only when `every_vehicle_must_visit` is false. |

Every rule, threshold, and formula from the sources is either implemented in `scripts/`,
stated in a step description or anti-pattern, or written in `references/model.md`.
