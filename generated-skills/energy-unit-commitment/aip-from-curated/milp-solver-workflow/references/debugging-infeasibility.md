# Debugging infeasibility

Load this when the solver returns infeasible, when the reported objective
disagrees with the recomputed objective, or when `run_all_checks` flags a
family that "should be" satisfied. The SKILL body cites this file from
the validation and repair steps.

## First suspect the model encoding, not the data

The data is usually fine; the encoding is usually wrong. Walk this
list before assuming the input is infeasible. In rough order of
likelihood:

* **Mixing total output with output above minimum.** Pick one
  convention in `pick-production-convention` (see
  `unit-commitment-data-modeling`) and stay in it. If `p` is
  above-minimum, balance must add `pmin * u` per period; if `p` is
  actual MW, segment widths refer to widths above `pmin`.
* **Applying startup/shutdown ramp limits to the wrong quantity.** The
  startup ramp limits `p[g, t]` when `u[g, t-1] = 0, u[g, t] = 1`. It
  does not limit `p` while the unit is already online. Encoding it as
  a hard cap on every transition row is a common bug.
* **Wrong `t` or `t-1` index.** Time-coupling rows
  (`u[t] - u[t-1] = start[t] - stop[t]`, ramp limits, min-up/down) are
  the easiest place to swap indices. Plug in a two-period hand case
  before trusting the row.
* **Over-constraining initial minimum up/down obligations.** If the
  source data does not say the unit owes any post-pre-horizon
  obligation, do not synthesise one. A unit that was on for one period
  pre-horizon and has `min_up = 4` does NOT necessarily owe three more
  on-periods at `t = 0` — only when the prompt extends the obligation.
* **Enforcing post-horizon obligations when the prompt excludes them.**
  `min-up` windows that extend past `T` are typically NOT enforced
  unless the prompt explicitly extends them. The bundled
  `check_min_up_down` validator follows this convention.
* **Treating cost curves as feasibility constraints.** Segment widths
  and slopes shape the cost objective; they do not bound dispatch.
  Encoding the highest segment's upper bound as if it were `pmax` makes
  any unit using its top segment infeasible.
* **Bad Big-M values.** Big-M rows of the form `something <= M * u`
  need `M` set to the smallest valid upper bound (typically `pmax` or
  `ramp`). `M = 1e9` makes the LP relaxation worthless; `M` too small
  cuts feasible solutions.
* **Requiring segment/tier variables when the trigger did not occur.**
  Startup-cost tiers only apply when the unit actually starts up;
  segment quantities only sum to a positive value when the unit is on.
  Tying their bounds to `start[g, t]` or `u[g, t]` is mandatory.

## Debug in stages

1. **Shapes.** Print `cb.family_summary()` and `vm.n`. The expected row
   counts for each family are `G * T` (per-resource per-period
   families) or `T` (system-wide families). A family one row short
   suggests an off-by-one in the index loop.
2. **Relax one family at a time.** Remove constraints by family until
   the model becomes feasible. The first family whose removal restores
   feasibility is the most likely culprit. Re-introduce its rows one
   block at a time to localize further.
3. **Diagnostic slack variables.** Add a non-negative slack to each
   suspect row (or each row in a suspect family) and put a large
   penalty on the slack in the objective. The solver will prefer to
   leave slacks at zero. Inspect the rows whose slack came back
   positive — they are the binding violations.
4. **Largest violations per family.** Once an incumbent (or any
   candidate vector) exists, call
   `scripts.sparse_constraints.largest_violations(...)` to surface the
   `top_k` worst rows per family. Cross-reference with the
   row-construction code to find the buggy term.
5. **Compare local validation with the final requirement.** A repair
   LP that omits a family judged in the final report can return
   "feasible" while the final validator returns "infeasible". The local
   and final validators must enforce the same family set.

## Repair LPs and heuristics

A fixed-commitment repair LP fixes the binaries (`u`, `start`, `stop`)
to a candidate schedule and solves the remaining LP. It is useful only
if it includes EVERY feasibility family judged in the final report.
Common omissions that produce "feasible" repairs that fail the final
check:

* Dropping joint reserve capacity (`p + r <= pmax * u`) — reserves get
  free upgrades that the final report rejects.
* Dropping transition-dependent ramp (`startup_ramp`, `shutdown_ramp`)
  — startup periods see ramps the final report rejects.
* Dropping minimum-duration tail enforcement at the start of the
  horizon — initial-state obligations get skipped.

Always rerun `run_all_checks` on the repaired incumbent. Never trust
the repair LP's status field as the final answer.

## When the data really is infeasible

Some prompts hand the agent infeasible inputs intentionally. Markers:

* `sum_g pmax[g]` in some period is less than `demand[t]` even with
  every unit online and reserve relaxed.
* Required reserve exceeds the largest unit's `ramp_up` summed across
  units committed by the prompt's prescribed schedule.
* Initial conditions force `min_up` obligations past the horizon end
  that the prompt then forbids relaxing.

When a data-side infeasibility is suspected, surface the precise row
that fails after every encoding suspect has been ruled out. Do NOT
return a `"pass"` self-check string with a relaxed objective; report
infeasibility with the violating rows attached.
