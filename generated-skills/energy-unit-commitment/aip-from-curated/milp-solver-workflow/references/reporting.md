# Reporting discipline

Load this from `write-final-output`. It captures the rules the final
report must satisfy independent of any solver behavior.

## Determinism

- Use deterministic ordering throughout — the generator order chosen in
  `parse-and-normalize-data` flows through every array and into the
  report's `thermal_generators` / `renewable_generators` lists.
- Hourly summary list is ordered by `hour` ascending, 1-indexed (period
  index 0 → `hour: 1`) unless the prompt says otherwise.
- Plain numeric values only. No `NaN`, no `inf`, no scientific notation
  unless required by precision. Cast numpy scalars with `float(x)` /
  `int(x)` before serializing — `json.dumps` rejects `np.float64` in
  some configurations.

## Numeric hygiene

- Round binaries only inside `extract-incumbent`; the report receives
  already-rounded `0` / `1` values.
- Do not emit a column with `-0.0`. Coerce `abs(x) < tol → 0.0`.
- Cost values: round only at write-time, never in the recompute. The
  recomputed objective is the truth; rounding for display is cosmetic.

## Solver status mapping

Map the solver's status code and the validation outcome to the report's
`solver_status` field:

- `optimal` — solver returned status 0 (HiGHS optimal) AND validation
  passed every family.
- `feasible` — incumbent exists, no proof of optimality, validation
  passed. Use this when the solver hit the time limit but produced a
  validated incumbent.
- `time_limit_feasible` — same as `feasible` but specifically driven by
  the configured `time_limit`.
- `suboptimal_feasible` — solver returned a non-optimal incumbent for a
  reason other than time limit (e.g., MIP gap target met).
- `heuristic_feasible` — schedule came from a heuristic or repair LP,
  not the main MILP solver.

A solver-reported `optimal` that fails validation is NOT `optimal` in
the report. Downgrade to `feasible` (or whichever heuristic path was
used) and fix the model.

## MIP gap

`reported_mip_gap` is a nonnegative number OR `null`:
- Set to the relative gap when both the incumbent objective and a
  reliable dual bound are available (HiGHS exposes `mip_dual_bound`
  through the SciPy result; `scripts/milp_helpers.py::solve_milp`
  computes it).
- Set to `null` when no reliable bound exists — heuristic solutions,
  repair LPs run after a separate commitment search, or solver outputs
  that do not expose `mip_dual_bound`.
- Never fabricate a gap. A common bug is reusing the configured
  `mip_rel_gap` target as the reported gap; that is a configuration, not
  a measurement.

## Constraint-check flags

The `constraint_check` block maps each family the report claims to
satisfy. Mark `"pass"` only when the matching family in
`validation-report` actually passed (read it from
`scripts/validation_checks.py::assemble_report`). The independent
verifier recomputes everything regardless; lying here only delays the
fix.

Common pitfalls:
- Marking `cost_consistency: "pass"` while the recomputed cost differs
  from the reported objective by more than the MIP gap.
- Marking `reserve_deliverability: "pass"` when the model never linked
  `p + r ≤ pmax * u` (the validation map asymmetry — see
  `references/patterns.md`).
- Marking `initial_conditions: "pass"` when the model's t=0 row used
  `u[:, -1]` instead of the case's `initial_commitment`.

## Schema discipline

Emit every field the output schema requires. If the schema allows
`null` for an unknown value, prefer `null` over `0`; a placeholder zero
silently passes downstream consumers that would otherwise raise.

Never include placeholder values "to be filled in later". The skill's
contract is that a written report is a final report.
