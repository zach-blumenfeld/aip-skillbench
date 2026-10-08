# bike-rebalancing-routing — provenance and compilation notes

## Provenance

Compiled 2026-10-08 from four curated Agent Skills, copied verbatim into this folder:

| Source | What it contributes |
| --- | --- |
| `geospatial-routing-data/SKILL.md` | ID↔index maps, coordinate checks, great-circle formula (radius 3960 mi), START/END arc set, route ID conversion, route-distance reconstruction, route data checks |
| `logistics-rules-to-optimization/SKILL.md` | Rule→constraint workflow, signed pickup/dropoff service pattern, station stock/space bounds, target-deviation slack, depot start/end (fixed or optional fleet), continuity, per-vehicle vs global single visit, load propagation, objective assembly, rule table |
| `routing-subtour-elimination/SKILL.md` | Why degree constraints allow subtours, MTZ, single-commodity connectivity flow, DFJ static/iterative cuts, method choice, route extraction with fail-fast |
| `scip-opt/SKILL.md` | Use PySCIPOpt (don't install another solver), modelling workflow, template, time/gap limits, require an incumbent, no `abs()` on expressions, reproducibility params, validate outside SCIP |

The four describe one workflow: parse geodata → translate rules → build SCIP routing MIP with subtour
elimination → extract and independently validate. The target environment (`inputs/environment`) is a
`python:3.12-slim` container with `pyscipopt==6.1.0` and one instance `/root/data.json` (2 vehicles,
capacity 25, penalty_weight 0.5, `great_circle_miles`, explicit sign convention "positive = pick up",
15 stations with `id, latitude, longitude, net_rebalancing_target, initial_bikes, station_capacity`).
Every loader default was checked against that exact file (key names, sign-convention sentence, metric
string, integer fields). The functional tests used a synthesized full-length file in the same format
plus the real file; no expected answer is hardcoded anywhere.

## Graph and step-kind choices

```
read-task (decision) → by-penalty-form (router) ─┬─ absolute_deviation / shortfall_only → solve (execution)
                                                 └─ other → adapt-model (client_task)
  → write-deliverable (client_task) → validate (execution) → by-verdict (router)
       pass → end · fail → fix-deliverable (client_task) → validate · unparsed → manual-check (client_task) → end
```

- **read-task — decision.** The model's switches (fleet fixed vs optional, split service across
  vehicles, return-empty, penalty form) are judgments over the task wording with a fixed answer space,
  so they are noul/choice questions, not prose. Numeric/path facts (data/output paths, initial truck
  load, Earth radius, time limit) are start inputs. Thresholds are set high (0.2 noul margin, 0.7
  choice confidence) because a wrong rule silently changes the optimum.
- **solve — execution.** All model logic is deterministic code (scripts/solve_rebalancing.py +
  scripts/rebalance_common.py): data parsing with ID maps, sign-convention parsing, great-circle
  distances, SCIP model, extraction, canonical report. Source logic placed here: visit linking,
  stock/space bounds, deviation slack, depot start/end, continuity, at-most-once, optional global
  single visit, load propagation, MTZ / flow SEC, reproducibility params, time/gap limits, incumbent
  check, route extraction with fail-fast, reconstructed-vs-SCIP objective check.
- **adapt-model — client_task.** Rules outside the two scripted penalty forms (squared deviation,
  fixed costs, time windows…) need new code; the agent edits a copy of the solver using the mirrored
  rule table in references/rules-to-constraints.md. Sets `custom_objective` so validation skips only
  the now-inapplicable penalty/objective recomputation.
- **write-deliverable — client_task.** The output schema is task-specific and unknown in advance;
  mapping canonical → task schema is generation. The template forces programmatic transformation.
- **validate — execution.** Independent recomputation from raw data (scripts/validate_report.py):
  route parsing from many common layouts, ID→index, depot labels, repeats, stop/route consistency,
  loads, end-empty, station stock/docks, split-service rule, distance/penalty/objective vs reported
  values and vs the solver's canonical objective. Emits `verdict` for the router.
- **fix-deliverable / manual-check — client_task.** Repair needs judgment about which side is wrong;
  hand-checking an unparseable layout is agent work. `waived_issues` is the escape hatch for genuine
  validator blind spots so the fail→fix→validate loop cannot spin forever.

## Deliberate deviations from the sources (improvements, all tested)

- **Pickup/dropoff as two non-negative integers** (`p`, `d`) instead of one signed `service` variable.
  Equivalent for routing, but lets station bounds be order-independent across vehicles
  (Σp ≤ initial bikes, Σd ≤ free docks), so no inter-vehicle timing assumption is needed. Reported
  per-stop values are netted (`pickup = max(p−d,0)` as in the source extraction rule).
- **Arc-flow truck load** (`y[v,i,j] ≤ Q·x[v,i,j]`, flow conservation = p−d) is the default; the
  source big-M load transition is kept as `load_model: bigm`. The arc-flow LP is much tighter.
- **Lifted MTZ** (Desrochers–Laporte) instead of plain MTZ; plain connectivity flow kept as
  `subtour_method: flow`. Truck load is never used for subtour elimination (source rule).
- **Root GSEC cut loop.** The source's "lazy/iterative DFJ cuts" idea, applied to the LP relaxation:
  max-flow/min-cut separation of generalized subtour cuts `Σ_{i∉S, j∈S} x ≥ visit_k`, iterated, then
  added statically to the MIP (no callback plumbing). On the real instance MTZ alone stalled at a
  6–9 % gap after 400 s; with the cuts SCIP proves optimality in ≈20 s.
- **Valid cut `dev_i ≥ |target_i|·(1 − Σ_v visit_i)`** and 2-cycle cuts `x_ij + x_ji ≤ 1`; symmetry
  breaking for identical vehicles (first-station index non-decreasing).
- `km` metric default radius 6371 added (source only gives miles/3960); data or task radius wins.

## Completeness check (source → location in the skill)

geospatial-routing-data: parse with a parser + duplicate-ID check → `rebalance_common.load_instance`;
indices in model, IDs in reports → solver extraction + anti-pattern; coordinate range checks →
`parse_location`; radians only in the distance function → `great_circle`; match metric/radius →
`resolve_radius` + `earth_radius` input; clamp cos → `great_circle`; do-not-mix list → anti-pattern;
START/END nodes and omitted START→END arc → solver `arcs` (+ `vehicles_must_be_used`); report↔index
conversion and "never assume 0..n−1" → `validate_report.to_idx` + anti-pattern; route distance
reconstruction, multi-vehicle sum, tolerance compare → `validate_report` (`close`); route data checks
(depot first/last, known IDs, ≥1 station, stop list = sequence, no repeats, recomputed distance) →
`validate_report`. Full text → references/geospatial-data.md.

logistics-rules-to-optimization: workflow and rule table → references/rules-to-constraints.md
(adapt-model); binaries for arcs, integers for counts → solver; visit from arcs → `visit`; tightest M
→ `min(Q, stock)` bounds; soft target/absolute deviation without `abs()` → `dev` + anti-pattern;
fixed vs optional fleet → `vehicles_must_be_used`; continuity/at-most-once per vehicle → solver;
global single visit only when required, never for large targets → `split_service_allowed` decision +
anti-pattern; load transition → arc-flow (big-M option); time windows → reference; signed
pickup/dropoff convention, stock/space limits, target deviation, extraction → solver + validator;
named objective components → solver report (`travel_distance`, `penalty_cost`).

routing-subtour-elimination: subtours despite degree constraints → MTZ/flow/GSEC + anti-pattern; base
constraints → solver; MTZ, flow, DFJ (as GSEC separation) → solver; pros/cons, method table → 
references/subtour-elimination.md; "don't use truck load for SEC" → anti-pattern; extract route and
fail fast on cycles/disconnection → solver extraction.

scip-opt: availability check, don't install another solver → solver import + anti-pattern; workflow
→ solver; `hideOutput`, time and gap limits, `getNSols()==0` failure → solver; reproducibility params
and single thread → solver; extraction + "feasibility necessary not sufficient" → validate step +
anti-pattern; template, binary activation, assignment patterns → reference.

## Deliberate-drop log

| Dropped from the procedure body | Rationale |
| --- | --- |
| Marketing/background prose ("SCIP is a strong open-source solver…", "the goal is not only routing…", lists of example domains) | Not actionable; still present verbatim in references/ and source/. |
| Generic examples unrelated to rebalancing (facility opening, assignment, mutually exclusive modes, precedence, route duration) | Not used by the scripted model; kept verbatim in references/rules-to-constraints.md for adapt-model. |
| Static DFJ enumeration and multi-commodity flow | Superseded by the GSEC separation loop; kept in references/subtour-elimination.md. |
| `/root/data.json` hardcoded path in source snippets | Replaced by the `data_path` input so any instance path works. |

No rule, threshold, condition, or lookup was dropped.

## Test log

- Real instance (`inputs/environment/data.json`): optimal, objective 8.8201, ≈20 s solve after the
  cut loop (vs. 8.834 incumbent at 6–9 % gap after 400 s with MTZ/flow alone).
- Synthetic full-length instance, rule variants (split forbidden, end-empty with initial load 5,
  optional fleet + shortfall-only, flow SEC): all optimal, validator pass.
- Validator negative test: internal index for an ID, overloaded truck, rounded total → all caught.
- Fresh-agent sessions (2): real file with a 0-based, pickups/dropoffs-dict schema → optimal 8.8201,
  but that session exposed a validator gap (vehicle-level quantity maps unread → waivers needed); fixed
  by parsing `pickups`/`dropoffs` dicts or record lists per vehicle, re-validated with no waivers.
  Stress file (3 vans, cap 15, flipped sign convention, optional fleet, no split, return empty,
  shortfall-only) → optimal, sign read correctly, validator pass. Template wording on return keys,
  vehicle numbering, and multi-vehicle service at one station clarified from their feedback.
- `aip run` end to end: pass branch (alternate schema), other→adapt-model→fail→fix→pass, and
  unparsed→manual-check on the real file.
