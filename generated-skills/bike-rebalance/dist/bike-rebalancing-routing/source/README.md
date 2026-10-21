# Source and provenance

`bike-rebalancing-routing` was compiled with the `skill-distillation` procedure from four curated
Agent Skills. They are copied verbatim here:

| Source | Contributed |
| --- | --- |
| `geospatial-routing-data/SKILL.md` | ID↔index mapping, coordinate checks, great-circle formula (R = 3960), depot_start/depot_end nodes, route conversion, distance reconstruction, route data checks |
| `logistics-rules-to-optimization/SKILL.md` | rule→constraint patterns, signed service variable, inventory bounds, soft target with absolute deviation, per-vehicle vs global visit rules, optional vehicles, objective assembly |
| `routing-subtour-elimination/SKILL.md` | base route constraints, MTZ, single-commodity flow, DFJ cuts, lazy separation, method choice, route extraction |
| `scip-opt/SKILL.md` | PySCIPOpt workflow, availability check, time/gap limits, require an incumbent, reproducibility params, independent validation |

The task framing (rules list, report schema, `/root/data.json`) comes from the benchmark task
statement the downstream agent receives. The container (`python:3.12-slim` + `pyscipopt==6.1.0`)
sets the dependency budget.

## Component-kind choices

| Component | Kind | Why |
| --- | --- | --- |
| Environment check | execution | Deterministic import/version check |
| Task-rule flags (`start_load_policy`, `every_vehicle_must_visit`, `split_service_allowed`) | decision (choice + 2 nouls) | Reading the prose statement takes judgment, but the answer space is fixed and maps 1:1 to script flags |
| Model build + solve + extraction + report arithmetic | execution (`scripts/solve_rebalance.py`) | All rules are deterministic constraints and calculations over data.json, and the solver is a maintained library (SCIP) |
| Status branching | deterministic rules in the body over script output | Simple if/then on `status`/`optimal`, with no judgment and no extra script |
| Rule validation | execution (`scripts/validate_report.py`) | Fixed rule set checked against the report, standard library only |
| Final answer to user | client task | Free text synthesis |

## Design decisions beyond the sources (found by functional testing)

- **Arc-flow load instead of big-M load propagation.** Source pattern: `load_j - load_i - s_j <= M(1-x)`.
  With that pattern plus MTZ or flow, the 15-station reference instance sat at an 8–12% gap after 300 s.
  The arc-flow form is the same rule with a tighter LP.
- **Lazy DFJ cuts by a PySCIPOpt constraint handler (default `--subtour cut`).** This is the source's
  "lazy callback" option, with fractional max-flow separation (generalized SECs). It proved
  optimality in about 11 s. The source's iterative re-solve loop was implemented first and ran out of
  time, so it was replaced (see drop log). MTZ and flow remain as `--subtour mtz|flow` fallbacks.
- **Dominance restriction is opt-in (`--dominance`), not default.** The source advises the
  "tightest possible M". Pushing that to "serve only toward the target" looked valid, but the
  functional test disproved it: with `--start-load zero`, the exact model reached 8.820138 and the
  restricted one 8.827783. An overshoot is penalty-neutral and can shorten routes. The exact
  per-stop bounds (initial bikes / free docks) are the default; the restriction is kept only as a
  timeout fallback.
- **Vehicle symmetry breaking** by route length (identical vehicles).
- **Default gap 0.0** instead of the source template's 0.01, so results are not 1% off a reference.
- **`start_load` free by default.** The task bounds start_load to `[0, capacity]` rather than fixing
  it at 0. Free gives 8.739 and zero gives 8.820 on the reference data (exact model), so it is a decision with
  "free" as the default and an explicit `zero` option.
- `--allow-idle-vehicles` keeps the `depot_start→depot_end` arc (equivalent to the source's
  `use_vehicle` binary, with fewer variables).
- `m.freeProb()` is called before returning so the Python constraint handler is not torn down after
  the model is gone. That teardown order raised a ReferenceError at exit.

## Deliberate-drop log

| Source content | Why dropped |
| --- | --- |
| logistics: assignment, facility-open, fixed vehicle cost, mutually exclusive modes, incompatible pairs, time windows, travel-time propagation, precedence, route duration rows, and their code examples | This task type has no such rules. The skill is scoped to depot pickup/dropoff rebalancing. The generic rule-translation workflow is kept implicitly in how the script is built and documented in references/model.md |
| logistics: "list entities / choose decision state" workflow prose | Generic modeling advice the agent already has. The concrete result is the formulation in references/model.md |
| scip-opt: assignment and binary-activation templates; "When To Use" bullets | Not needed for this model. Activation appears as service ≤ bound·visit |
| subtour: static DFJ enumeration code | Exponential. Superseded by lazy DFJ cuts. Mentioned in references/model.md as a debugging baseline for ≤15 stations |
| subtour: iterative re-solve DFJ loop code | Implemented and tested, but it ran past the time limit on the reference instance. The constraint handler does the same separation lazily inside one solve |
| subtour: multi-commodity flow row of the method table | Not implemented (too many variables, as the source says). Noted in references/model.md |
| geospatial: code snippets for parsing/conversion | Carried as code in both scripts rather than as prose |
