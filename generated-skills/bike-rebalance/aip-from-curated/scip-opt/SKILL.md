---
name: scip-opt
description: SCIP optimization with PySCIPOpt. Use when facing an optimization problem with an objective, hard constraints, soft penalties, integer decisions, routing, assignment, scheduling, allocation, packing, capacity, inventory, or service-level rules. Prefer modeling and solving the problem with PySCIPOpt when it is available.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Solve mixed-integer optimization problems with PySCIPOpt. SCIP is a strong
  open-source solver well suited for routing, assignment, capacity planning,
  inventory movement, scheduling, and problems with soft penalties. For
  benchmark and report-style tasks, a SCIP-backed model paired with an
  independent validator is safer than a hand-written greedy construction.

trigger_when:
  - Task asks to minimize or maximize an objective such as cost, distance, time, unmet demand, or penalty.
  - Decisions are yes/no choices, route arcs, assignments, selected items, or orderings.
  - Quantities involved are integer or continuous (load, inventory, flow, served units, slack).
  - Hard rules every valid answer must satisfy (capacity, conservation, bounds, linking, mutual exclusion).
  - Soft rules that may be violated with an explicit penalty.
  - Routing, assignment, scheduling, allocation, packing, capacity, inventory, or service-level problems.

do_not_use_when:
  - PySCIPOpt is not importable and cannot be installed within the runtime constraints — fall back to a documented heuristic and say so.
  - The instance is trivially small and a closed-form or single-pass greedy is provably optimal.

scope_and_approval: >
  Read-only against the input data; writes only the agent's own modeling
  artefacts and the requested report file. No external services. Re-run the
  reproducibility helper whenever results must be repeatable across runs
  (benchmarks, oracle comparisons, regression tests).

steps:
  - name: verify-pyscipopt
    description: Confirm PySCIPOpt is importable before building a model; do not install a different optimization package as a first move.
    script: scripts/check_pyscipopt.py
    outputs:
      - name: pyscipopt-available
        type: boolean
        description: True when `from pyscipopt import Model, quicksum` succeeds.

  - name: identify-sets-and-indices
    description: >
      Enumerate the problem's sets and indices (vehicles K, stations N, jobs
      J, periods T, arcs A, …). Build explicit ID-to-index mappings when
      input identifiers are not contiguous.
    depends_on: [verify-pyscipopt]
    inputs:
      - name: problem-data
        type: object
        description: Parsed input describing entities, capacities, targets, costs.
    outputs:
      - name: sets-and-indices
        type: object
        description: Named index sets plus any ID-to-index mappings the model will use.

  - name: define-decision-variables
    description: >
      Declare binaries for choices / visits / assignments / arcs / modes;
      integers for counts, loads, inventory moves, and unmet units;
      continuous variables for flows, costs, times, slacks, or resource
      levels. See `references/template.md` for a worked scaffold.
    depends_on: [identify-sets-and-indices]
    inputs:
      - name: sets-and-indices
        type: object
    outputs:
      - name: variables
        type: object
        description: Map of variable family name to its SCIP variable dict.

  - name: add-hard-constraints
    description: >
      Add conservation, capacity, bounds, linking, continuity, inventory
      limits, and mutual-exclusion constraints. Load `references/patterns.md`
      for binary-activation, assignment, route-arc, and MTZ subtour-elimination
      snippets. Routing models need subtour elimination — degree + continuity
      alone permit disconnected cycles.
    depends_on: [define-decision-variables]
    inputs:
      - name: variables
        type: object
      - name: problem-data
        type: object
    outputs:
      - name: hard-constraints-added
        type: boolean

  - name: add-soft-constraints
    description: >
      Express soft rules with explicit non-negative slack variables.
      Linearise absolute deviation with two inequalities (see the
      "Absolute deviation penalty" snippet in `references/patterns.md`).
      Never call Python's built-in `abs()` on a SCIP expression.
    depends_on: [define-decision-variables]
    inputs:
      - name: variables
        type: object
    outputs:
      - name: slack-variables
        type: object
        description: Slack variable family keyed by the rule it relaxes.

  - name: set-objective
    description: >
      Set a single SCIP objective composed of named components (e.g.,
      `travel_cost`, `penalty_cost`). Keep each component as a separate
      `quicksum` expression so it can be recomputed independently in the
      validation step.
    depends_on: [add-hard-constraints, add-soft-constraints]
    inputs:
      - name: variables
        type: object
      - name: slack-variables
        type: object
    outputs:
      - name: objective-components
        type: object
        description: Named expressions whose sum is the SCIP objective.

  - name: configure-reproducibility
    description: >
      Apply SCIP randomization and threading settings so results repeat
      across runs. The helper applies the parameter list with graceful
      fallback for SCIP versions that rename a setting.
    script: scripts/configure_reproducibility.py
    depends_on: [set-objective]
    inputs:
      - name: model
        type: object
    outputs:
      - name: reproducibility-params-applied
        type: list[string]

  - name: solve
    description: >
      Set time and gap limits (e.g. `limits/time=300`, `limits/gap=0.01`),
      call `model.optimize()`, then require at least one incumbent
      (`model.getNSols() > 0`) before extracting variable values. Treat a
      non-zero status alone as insufficient.
    depends_on: [configure-reproducibility]
    inputs:
      - name: model
        type: object
    outputs:
      - name: solve-status
        type: string
      - name: incumbent-found
        type: boolean

  - name: reconstruct-and-validate
    description: >
      Reconstruct the answer from variable values (compare binaries against
      0.5, round integers explicitly). Recompute every named objective
      component and every hard rule from the reconstructed solution and
      assert it matches what the model reported (tolerance 1e-6). See
      `references/validation.md` for the full check list (schema, route,
      capacity, conservation, penalty arithmetic, objective arithmetic).
      Treat SCIP feasibility as necessary but not sufficient.
    depends_on: [solve]
    inputs:
      - name: model
        type: object
      - name: variables
        type: object
      - name: objective-components
        type: object
    outputs:
      - name: report
        type: object
        description: Final structured answer (e.g., `report.json`) after independent validation passes.

anti_patterns:
  - Reaching for a different optimization package before checking whether PySCIPOpt is already available.
  - Calling Python's built-in `abs()` on a SCIP expression — linearise with two `<=` inequalities and a non-negative slack instead.
  - Modeling routing with only degree and continuity constraints — disconnected sub-cycles will appear; add MTZ (or stronger) subtour elimination.
  - Reading variable values after `model.optimize()` without checking `model.getNSols() > 0` — status alone is not enough.
  - Treating SCIP feasibility as proof the report is correct — always reconstruct the answer and recompute every objective component and hard rule independently.
  - Using an arbitrary big-M in linking constraints when a real upper bound (capacity, max distance, horizon) is available.
  - Patching the report to make numbers reconcile instead of fixing the underlying model or extraction bug.
```
