---
name: uc-day-ahead-milp
description: Solve day-ahead / multi-period thermal unit commitment (UC) from structured case data (pglib-uc style JSON or convertible tables) as a MILP with SciPy/HiGHS. Builds commitment, startup/shutdown, dispatch and spinning-reserve schedules with minimum up/down, ramping, startup/shutdown capability, reserve deliverability, initial conditions, must-run, renewable curtailment, piecewise production and tiered startup costs; validates the schedule independently and writes a JSON report with recomputed cost, MIP gap and constraint checks.
compatibility: Python >= 3.9 with numpy >= 1.22 and scipy >= 1.9 (scipy.optimize.milp / HiGHS). No other packages or tools.
---

# Day-Ahead Unit Commitment via MILP

## Trigger When

- A task asks for a day-ahead or multi-period unit commitment schedule (thermal on/off, dispatch, spinning reserve) from a structured case file (e.g. a pglib-uc style JSON network/case file).
- The data has thermal generators with min/max output, ramp, min up/down, initial status, startup tiers and piecewise production costs, plus hourly demand, reserve and renewable bounds.
- A UC schedule or report must be checked for feasibility (balance, reserve, ramping, min up/down, startup/shutdown logic) or its cost recomputed.
- More broadly: a time-expanded scheduling problem with binary on/off decisions solved with an open-source MILP solver.

## Purpose

Turn a single-zone UC case (no network flows, no contingencies) into a feasible, economical schedule and a report the task's verifier accepts. The skill carries a tested MILP (tight pglib-uc-style formulation: above-minimum dispatch, joint production+reserve capability with startup/shutdown limits, reserve-inclusive ramping, tiered startup costs keyed on offline duration, initial-condition obligations), an independent validator that re-derives every constraint family from the report arrays, and the conventions agents usually get wrong (actual vs above-minimum MW, reserve deliverability, t0 handling).

## Before the first script

Check that `python3` (>= 3.9) imports `numpy` and `scipy` with `scipy.optimize.milp` available (`python3 -c "from scipy.optimize import milp"`). Name everything missing. Do not pip-install other solvers; HiGHS through SciPy is the solver.

All commands below run from this skill's folder. `<case-json>` is the case file path and `<report-json>` the required report path, both as the task states them (e.g. container paths).

## Step 1 — Read the task statement (decision)

Answer from the task prompt, in one pass. Each answer maps to a `solve` flag.

```yaml
hour_label_start:
  type: choice
  instructions: What label does the first period carry in the report's hourly summary?
  criteria:
    "1": The prompt says hours start at 1, or gives no rule (default).
    "0": The prompt explicitly says the first hour is 0.
production_convention:
  type: choice
  instructions: What must the reported per-unit production be?
  criteria:
    actual: Total MW produced by the unit (default; "actual value", "total MW", "not output above minimum").
    above_min: The prompt explicitly asks for output above minimum.
renewable_curtailment:
  type: noul
  instructions: May renewables produce anywhere between their hourly minimum and maximum?
  criteria:
    true: The prompt allows curtailment or is silent (data min/max bounds govern).
    false: The prompt requires all available renewable energy to be used (output fixed at the maximum).
```

A wrong answer silently corrupts the report; reconsider any close call against the literal prompt wording. Flags: `--hour-start <hour_label_start>`, `--production-convention <production_convention>`, and add `--no-curtail` only if `renewable_curtailment` is false.

Also confirm the scope the script implements matches the prompt: single system balance (demand + spinning reserve hourly), reserve only from online thermal units, no branch flows or contingencies, no data removal or rescaling. If the prompt adds a rule the script lacks, extend the model and the validator together (see `references/formulation.md`).

## Step 2 — Inspect the case (script)

```bash
python3 scripts/uc_milp.py inspect <case-json>
```

Prints T, unit counts, demand/reserve range, thermal capacity, units on at t0, must-run units, curtailable renewable cells, nonconvex curves, tier counts; then parser warnings/errors.

- exit 0 → Step 3.
- exit 2 (schema mismatch: listed missing keys) → client task: write a converter from the given format to the canonical JSON in `references/data-format.md` (read it now). Map concepts by meaning, units and shape; preserve names and source order; do not rescale or drop data. Save the converted file in a scratch location (not in this skill folder), rerun `inspect` on it until exit 0.
- exit 3 (data inconsistency, e.g. lengths != T, pmin > pmax, t0 output inconsistent with status, curve not spanning [pmin, pmax]) → report the listed errors; fix only genuine parsing mistakes in your converter, never the task's data.

## Step 3 — Solve, validate, write (script)

```bash
python3 scripts/uc_milp.py solve <case-json> --out <report-json> \
    --hour-start 1 --production-convention actual [--no-curtail] [--time-limit 300] [--mip-gap 1e-3]
```

The script builds the MILP, solves with HiGHS, rounds near-integral binaries (aborts if any is fractional), re-derives startup/shutdown from commitment, converts to actual MW, recomputes cost from the arrays, runs the independent validator, and writes the report only when every family passes (then all `constraint_check` values are `"pass"`). Report fields: `solver_status` (`optimal` | `time_limit_feasible`), `objective_cost` (recomputed), `reported_mip_gap` (HiGHS gap, `null` if unavailable), counts, per-unit arrays in source order, `hourly_summary` with demand, thermal and renewable generation, reserve requirement and scheduled reserve.

Runtime is about `--time-limit` + 10 s. Give the shell call a timeout above that, or run it in the background; if your tool timeout is shorter, lower `--time-limit`. On the reference 73-thermal / 81-renewable / 48-hour case HiGHS finds a ~0.6% incumbent in ~20 s and ends `time_limit_feasible` at 0.35–0.6% after 300 s; progress varies run to run. Longer runs give small gains, because the remaining gap is mostly the bound. 24-hour cases often prove `optimal` in under a minute.

## Step 4 — Judge the outcome (decision)

Input: the `solve` console output (status line, gap, validation table, exit code) and your remaining time budget.

```yaml
solve_action:
  type: choice
  instructions: What to do with this solve result?
  criteria:
    accept: Exit 0 and status optimal, or time_limit_feasible with gap <= 0.005, or any feasible result when there is no time left for another run.
    rerun_longer: Exit 0, status time_limit_feasible, gap > 0.005 (or null) and time remains; rerun with a larger --time-limit (e.g. double) writing to a different --out, then keep the lower-cost report at the required path.
    debug: Exit 1 (validation FAIL), or "no incumbent" / fractional-binary error.
```

A `time_limit_feasible` result with exit 0 is a valid, fully validated schedule; on a rerun keep whichever report has the lower `objective_cost`. Accepting a poor-gap schedule costs economy; rerunning costs time. Lean to `rerun_longer` only when the budget clearly allows it. For `debug`: on "no incumbent", rerun the same `solve` command with `--diagnose` added. It adds priced balance and reserve slacks and prints the hours that need them (generation shortfall or surplus, reserve shortfall). If no slack is used, the conflict is in unit-level rules. Then read `references/formulation.md` (constraint map and infeasibility checklist). On a validation FAIL, the failing report is saved next to the requested output with a `FAILED` suffix, for inspection. Never hand-edit `"pass"` strings or numbers into a report.

## Step 5 — Re-check the final file (script)

```bash
python3 scripts/uc_milp.py validate <case-json> <report-json> [--production-convention actual]
```

Exit 0 with every family `pass` is required before finishing; run it after any manual change, converter fix, or rerun. It reads only the case and the report.

## Gotchas

- Reported production is actual MW (`pmin*u + above_min`); ramping and startup/shutdown capability apply to above-minimum output plus reserve. Mixing the two conventions is the most common bug.
- Reserve is not unused nameplate: it must fit under pmax with production, under the startup limit in a startup period, under the shutdown limit in the period before a shutdown, and within ramp-up from the previous period. Units with `ramp_startup_limit == pmin` carry zero reserve when starting.
- Offline units have zero production and zero reserve; renewable headroom never counts as reserve.
- Initial conditions: first-period ramps use `power_output_t0`; remaining min-up/down obligations are `time_up_minimum - time_up_t0` / `time_down_minimum - time_down_t0`; startup tier for an initially-off unit uses `time_down_t0 + t - 1` periods offline.
- Production cost is the total-cost curve evaluated at actual MW (first point = online minimum-output cost). Do not add no-load, reserve, curtailment or shutdown costs not in the data.
- Do not trust the solver status or `"pass"` strings alone; the validator is the gate.
