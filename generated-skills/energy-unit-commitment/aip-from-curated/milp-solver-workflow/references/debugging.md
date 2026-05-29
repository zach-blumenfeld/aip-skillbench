# Debugging infeasibility & repair LPs

Load this when `solve-milp` returns no incumbent, when the solver claims
optimal but `validate-independently` flags a family, or when running the
`repair-from-fixed-commitment` mode.

## First suspect: the model encoding

When the solver returns infeasible or "no incumbent", the cause is almost
always a row in the model, not a solver bug. The patterns that produce
silent infeasibility most often:

- Mixing total output `p` with output-above-minimum `p - p_min * u` in
  different rows. Pick one internal convention and apply it consistently.
- Applying startup or shutdown capability limits to total output `p`
  instead of the transition quantity `p - p_min * u`.
- Off-by-one on `t` vs `t-1`. Ramp and transition rows reference both;
  initial-period rows need a separate code path that consumes the case's
  `initial_*` fields, not `u[:, -1]` or `p[:, -1]`.
- Over-constraining initial obligations — forcing `u[g, t]==1` for *all*
  `t < min_up[g]` instead of only the leftover obligation
  `min_up[g] - initial_uptime[g]`.
- Enforcing post-horizon obligations the prompt did not require
  (e.g., requiring min-down to extend past period T).
- Treating cost-curve rows as feasibility constraints — segment
  activation must follow from the production link, not be forced.
- Bad Big-M values. Use the tightest physically meaningful constant
  (typically `pmax`) and never an arbitrary large number.
- Requiring segment / tier variables when the trigger condition did not
  occur (e.g., charging segment cost when `u==0`).

## Staged relaxation

Drop one family at a time and re-solve:

1. Relax min-up / min-down. If feasible, the bug is in those rows or the
   initial-condition handling.
2. Otherwise relax ramping. If feasible, suspect the ramp surcharge for
   startup/shutdown or the `t-1` indexing.
3. Otherwise relax joint reserve capacity. If feasible, suspect the
   `p + r ≤ pmax * u` encoding (sign error or wrong pmax).
4. Otherwise relax startup/shutdown linking. If feasible, the linking row
   is wrong (the equality should be `u[t] - u[t-1] == start[t] - shutdown[t]`).
5. Otherwise check the balance row. Equality balance with renewables and
   load profiles is the last family to relax — if removing it makes the
   problem feasible, the demand/supply totals are inconsistent with
   capacity.

The first family whose removal restores feasibility is the prime
suspect — investigate there before relaxing further.

## Diagnostic slacks

When staged relaxation does not localize the bug, add nonnegative slack
variables to each suspect family with a large positive objective
coefficient (cost the slack so the solver prefers true feasibility).
Solve and print which slacks are nonzero. The pattern of nonzero slacks
points at the offending row.

## Sanity checks before re-solving

- Print `var_map.n`, the number of constraint rows, and the shape of each
  decision block. Mismatches against `(G, T)` usually trace to a `reshape`
  or `np.arange` indexing bug.
- Hand-test a single row: set the relevant inputs by hand, evaluate the
  row, and confirm it matches the intended inequality (see
  `references/patterns.md` § Sign-Safe Encoding).
- Compare local validation against final-reporting requirements. If the
  validator is stricter than the model (e.g., the validator requires
  reserve deliverability but the model never linked `p + r`), the model
  must be extended.

## Repair LPs

A fixed-commitment repair LP is useful only if it includes every
feasibility family the final report is judged against. Do NOT repair
only balance + capacity and skip ramp, reserve deliverability,
startup/shutdown capability, or minimum durations — the repaired
schedule will pass the LP and fail independent validation.

Construction:
1. Take the candidate commitment `u_hat`, startup `start_hat`, shutdown
   `shutdown_hat` and pin them: `lb = ub = u_hat` for those columns.
2. Keep `p`, `r`, and any cost-segment variables free with their original
   bounds.
3. Re-add every constraint family that does NOT involve binary decisions
   the commitment already fixes — balance, capacity, joint reserve, ramp
   deliverability, renewable bounds, cost-curve linking.
4. Solve as a pure LP (set `integrality` to 0 for the still-free vars;
   binaries are already pinned).
5. Run `validate-independently` against the repaired arrays. If it fails,
   the repair LP was missing a family — extend it.

Heuristic shortcuts (priority-list dispatch, greedy commit-when-needed,
Lagrangian relaxation) are appropriate fallbacks when the full MILP
returns no incumbent within the time limit. They MUST also pass
independent validation; do not write `"pass"` strings based on the
heuristic's internal feasibility logic.
