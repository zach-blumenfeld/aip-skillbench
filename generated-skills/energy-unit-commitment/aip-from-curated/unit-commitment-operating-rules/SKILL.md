---
name: unit-commitment-operating-rules
description: Use for day-ahead or multi-period unit commitment problems, including thermal on/off schedules, dispatch, startup/shutdown logic, minimum up/down time, ramping, spinning reserve deliverability, renewable curtailment, operating-cost accounting, and independent feasibility checks for power-system operations schedules.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3. The bundled validators are standard-library only — no numpy or solver required.
---

```yaml
purpose: >
  Reusable operating-rules guide for day-ahead or multi-period unit
  commitment. Covers how to keep production, reserve, and transition
  variables consistent; how to encode hard feasibility (capacity, offline
  zeros, transitions, reserve deliverability, ramping, min up/down,
  demand balance, renewable bounds, system reserve); and how to recompute
  startup and production costs from arrays after the schedule is
  extracted. Bundled scripts encode the validation rules and cost
  decision-rules so the agent runs the same checks the operator would.
  This is a formulation and validation guide — not a complete
  task-specific mathematical model.

trigger_when:
  - Day-ahead or multi-period unit commitment is requested with generators, load, reserves, operating constraints, and cost tradeoffs.
  - A schedule has been produced and needs independent feasibility verification before being reported.
  - Reserve deliverability, ramping, min up/down, or startup-tier costs need to be reasoned about carefully.
  - The output convention (actual MW vs above-minimum MW) needs to be locked before encoding constraints or costs.
  - Operating costs (startup, production) must be recomputed from extracted arrays to populate report fields.

do_not_use_when:
  - The task is a single-period economic dispatch with no commitment, ramping, reserve, or initial-state coupling.
  - The task is purely about market clearing, settlements, or pricing rather than physical schedule feasibility.
  - The task is about long-term expansion planning, AC power flow, or stability — not operations scheduling.

scope_and_approval: >
  Read-only with respect to task data. The validator and cost helpers
  return reports; they do not mutate the schedule. The agent may write
  the recomputed costs and `"pass"` flags into the report only after
  `scripts/feasibility_checks.py` returns `ok=True`. No network access
  required.

steps:
  - name: parse-and-normalize
    description: >
      Build uniform per-resource, per-period arrays from the task data.
      Every resource appears exactly once; every time series has length
      T. Capture the initial state for each thermal unit
      (`initial_on`, `initial_above_min` or initial actual output,
      `initial_on_duration`, `initial_off_duration`). Capture per-unit
      `pmin`, `pmax`, `ramp_up`, `ramp_down`, `min_up`, `min_down`,
      `startup_limit` (if given), `startup_cost_tiers`, the production
      cost curve, and any `must_run` periods. Capture system `demand[t]`
      and `reserve_requirement[t]`, plus per-renewable `min[t]` /
      `max[t]`.
    outputs:
      - name: schedule_inputs
        type: object
        description: Normalized per-resource, per-period arrays plus initial state.
      - name: system_spec
        type: object
        description: Per-unit parameters, demand, reserve requirement, renewable bounds.

  - name: choose-output-convention
    description: >
      Pick exactly one production variable convention for the whole
      model — either actual MW or above-minimum MW — and record it
      next to the model. Do not mix conventions inside ramping,
      reserve deliverability, cost evaluation, or reporting. Reports
      usually require actual MW; convert at extraction time if the
      internal model uses above-minimum.
    one_of:
      - actual-MW production
      - above-minimum production
    depends_on: [parse-and-normalize]
    outputs:
      - name: production_convention
        type: string
        description: Either "actual" or "above_min".

  - name: encode-hard-constraints
    description: >
      Encode every operating constraint before any cost objective.
      Required families, in algebraic form (see
      `references/constraint-patterns.md` for the exact patterns and
      code snippets): (1) commitment/startup/shutdown binaries and
      `u - prev_u == start - stop`; (2) capacity bounds with offline
      zeros for production and reserve; (3) joint reserve
      deliverability — production-plus-reserve under capacity, with
      startup-period tightening when `startup_limit` is provided;
      (4) ramp up/down across periods using the unit's pre-horizon
      output for `t = 0`, and apply ramp-up to production-plus-reserve;
      (5) min up/down across periods, including pre-horizon carryover
      from `initial_on_duration` / `initial_off_duration`; (6) demand
      balance per period using the prompt's nodal/zonal convention;
      (7) renewable per-period bounds (`min[t] <= output <= max[t]`);
      (8) system reserve requirement met by thermal reserve only —
      do not count renewable headroom unless the prompt explicitly
      allows it; (9) any must-run periods.
    depends_on: [choose-output-convention]

  - name: solve-or-construct
    description: >
      Solve the MILP or construct a heuristic schedule honoring the
      hard constraints. Cost objective uses only the components
      present in the data — production cost curve and startup tiers.
      Do not invent no-load, reserve, curtailment, shutdown, or
      ramping costs.
    depends_on: [encode-hard-constraints]
    outputs:
      - name: raw_solution
        type: object
        description: Decision-variable values from the solver or heuristic.

  - name: extract-into-report-arrays
    description: >
      Extract the decision variables into the report convention. If
      the report demands actual MW and the model used above-minimum,
      compute `actual = pmin * u + p_above_min` resource by resource.
      Build the typed schedule object expected by
      `scripts/feasibility_checks.py` (see its module docstring for the
      data contract).
    depends_on: [solve-or-construct]
    inputs:
      - name: raw_solution
        type: object
    outputs:
      - name: schedule
        type: object
        description: Per-resource arrays in the report convention; ready for validation.

  - name: run-feasibility-validation
    description: >
      Run the bundled validator. It checks: resources appear exactly
      once; all time-series have length T; commitment, startup, and
      shutdown are binary; offline thermal units have zero production
      and zero reserve; online units respect min/max; must-run units
      are online when required; startup/shutdown match commitment
      transitions; demand balance holds in every period; renewable
      output stays within period-specific bounds; scheduled reserve
      meets the system requirement; reserve is jointly deliverable
      under headroom, startup capability, and ramp limits; ramp
      up/down are honored using pre-horizon output for the first
      period; minimum up/down time accounts for pre-horizon on/off
      duration. Stop and repair the schedule if `ok=False` — never
      paper over errors.
    script: scripts/feasibility_checks.py
    depends_on: [extract-into-report-arrays]
    inputs:
      - name: schedule
        type: object
      - name: system_spec
        type: object
      - name: production_convention
        type: string
    outputs:
      - name: feasibility_report
        type: object
        description: '{"ok": bool, "errors": [...], "warnings": [...], "totals": {...}}.'

  - name: recompute-startup-cost
    description: >
      For each thermal unit, recompute total startup cost from the
      `start` array and the tier table — never trust solver internals
      to populate the report. The tier rule applies the LARGEST `lag`
      not exceeding the offline duration immediately before the
      startup; the helper tracks offline duration across the horizon
      using the unit's pre-horizon initial state.
    script: scripts/startup_cost.py
    depends_on: [run-feasibility-validation]
    inputs:
      - name: schedule
        type: object
      - name: system_spec
        type: object
    outputs:
      - name: startup_cost_per_unit
        type: object
      - name: total_startup_cost
        type: float

  - name: recompute-production-cost
    description: >
      Recompute total production cost from the actual-MW output array
      using the piecewise-linear total-cost curve. The cost at each
      breakpoint is the TOTAL cost at that output level (not
      marginal). Clamp to the endpoint cost outside the curve;
      interpolate linearly between adjacent breakpoints. If the
      smallest breakpoint is at `pmin`, its cost may already cover the
      online minimum-output cost — do not add a separate fixed online
      cost unless the data says so. Offline periods contribute zero.
    script: scripts/production_cost.py
    depends_on: [run-feasibility-validation]
    inputs:
      - name: schedule
        type: object
      - name: system_spec
        type: object
    outputs:
      - name: production_cost_per_unit
        type: object
      - name: total_production_cost
        type: float

  - name: write-report
    description: >
      Populate the report. Set `"pass"`-style flags only when the
      feasibility report has `ok=True` and `len(errors)==0`. Costs and
      summaries are taken from `recompute-startup-cost` and
      `recompute-production-cost`, not from solver objective values.
      Forward any non-empty warnings into the report so the operator
      sees them.
    depends_on:
      - recompute-startup-cost
      - recompute-production-cost
    inputs:
      - name: schedule
        type: object
      - name: feasibility_report
        type: object
      - name: total_startup_cost
        type: float
      - name: total_production_cost
        type: float
    outputs:
      - name: report
        type: object

scenarios:
  - need: A 24-hour UC instance with three thermal units, one wind farm, hourly demand, and a 10%-of-load spinning reserve requirement.
    context: >
      Solver returns a schedule. The agent must validate it before
      reporting cost or pass flags.
    action: >
      Extract per-unit arrays in actual-MW convention. Call
      `scripts/feasibility_checks.py` with
      `production_convention="actual"`. With `ok=True`, recompute
      startup cost via `scripts/startup_cost.py` (offline duration
      includes the unit's pre-horizon hours-off), and production cost
      via `scripts/production_cost.py` against the unit's
      piecewise-linear curve.
    outcome: >
      Report fields are populated from the recomputed totals; the
      `"pass"` flag is set only because every constraint family
      validated.
  - need: A schedule that looks fine on headroom but fails reserve deliverability.
    context: >
      `reserve[g, t] <= pmax[g] - production[g, t]` and
      `reserve[g, t] <= ramp_up[g]` both hold individually, but a
      unit was just started in period `t` with `startup_limit < pmax`.
    action: >
      The validator flags `startup capability at g t=t:
      production+reserve > startup_limit`. The agent reduces reserve
      on the starting unit and reallocates it to another online unit
      with headroom, then re-runs the validator.
    outcome: >
      Validator returns `ok=True`. The schedule no longer assumes the
      starting unit can deliver reserve it cannot physically provide.
  - need: A unit with min_up = 4 was online at t = -1 for only one prior hour.
    context: >
      `initial_on = 1`, `initial_on_duration = 1`. The schedule turns
      the unit off at t = 1.
    action: >
      The validator flags "min_up not satisfied carrying initial-on
      at g t=1": the unit must remain on for three more periods (4
      total − 1 carried). The agent keeps the unit online through
      t = 2 and re-validates.
    outcome: >
      Min up/down checks pass. The fix would have been missed by a
      validator that only checked within-horizon starts.

anti_patterns:
  - Treating unit commitment as independent hourly economic dispatch — startup, ramping, reserve deliverability, min up/down, and initial conditions all couple period to period.
  - Counting reserve from offline units or from renewable headroom. Offline units contribute zero reserve; renewable headroom only counts when the prompt explicitly allows it.
  - Checking reserve only against headroom while ignoring startup-period capability or ramp limits. Use joint production-plus-reserve constraints (and startup-limit tightening when `start[g, t] == 1`).
  - Ignoring initial output when checking ramping at `t = 0`. The unit's pre-horizon output is what bounds the first-period change.
  - Ignoring pre-horizon on/off duration when checking minimum up/down time. A unit on for only one period at `t = -1` still owes `min_up - 1` periods online inside the horizon.
  - Mixing actual-MW and above-minimum-MW conventions inside the same model. Lock one in `choose-output-convention` and convert only at extraction.
  - Inventing cost components not present in the data. Use only the production cost curve and the startup tier costs the prompt provides. No no-load, reserve, curtailment, shutdown, or ramping cost unless stated.
  - Trusting a repair LP that quietly drops a constraint family. Always re-run `scripts/feasibility_checks.py` after any repair.
  - Hard-coding `"pass"` fields before validation. Set them only after the validator returns `ok=True` with no errors.
```
