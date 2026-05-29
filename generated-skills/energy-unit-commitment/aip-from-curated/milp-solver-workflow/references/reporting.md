# Reporting discipline

Load this when assembling the final solution report. The SKILL body
cites this file from the extraction and write-final-output steps.

## Determinism

* Use deterministic ordering. Resource arrays follow source order
  (carried in `*_names` lists from the parsed case). Period arrays
  follow `0..T-1`. JSON dicts use sorted keys at write time.
* Plain numeric values: `int`, `float`. No numpy scalars in the
  serialised output. Cast with `int(x)` / `float(x)` at the boundary —
  `numpy.int64` may serialise as a string, and downstream comparators
  fail silently.
* No placeholder values. If a field is genuinely absent (no reliable
  MIP gap, no startup cost data), use `null` if the schema allows it
  or omit the field entirely. A `0` placeholder reads as "the answer
  is zero" and corrupts downstream analysis.

## Feasibility versus proof quality

Keep these distinct in the final report:

* **Feasibility** = `run_all_checks(...)["ok"]`. Set the report's
  `feasible`/`status` field from this, not from the solver status.
* **Proof quality** = `solve_result.mip_gap`. Write the gap exactly as
  the solver reports it (or `null` when no reliable bound is
  available). Never back-compute a gap from the incumbent alone.

A time-limit hit with a feasible incumbent yields
`feasible = True, mip_gap = <some positive number>`. A solver-side
infeasible status with a stale incumbent yields
`feasible = False` regardless of the solver's gap claim.

## Self-check strings

If the prompt's schema accepts a self-reported `"pass"` / `"fail"`
string, only write `"pass"` AFTER `run_all_checks(...)["ok"]` is True.
A solver-reported "feasible" status is NOT sufficient evidence; the
solver only knows about the constraints actually encoded in `A`, and a
bug in the encoding can produce a "feasible" solver report that the
independent validator rejects.

If validation fails, the report must surface:

* The list of failing families.
* For each failing family, the top-k violations (resource index,
  period index, magnitude). Use the bundled helpers' return shape; do
  not reformat into prose.
* The recomputed objective and the solver objective if they differ
  beyond tolerance.

## What the report MUST include

Every prompt's output schema differs in exact field names. The
universal contents are:

* Per-resource per-period commitment and dispatch arrays (and reserve
  when the problem has reserve).
* Per-period demand satisfaction and reserve satisfaction summaries
  (so the report stands alone without re-reading the inputs).
* The total objective at the reported solution.
* The feasibility verdict from independent validation.
* The proof-quality fields when available (solver status, best bound,
  MIP gap, solve wall time).
* Source resource and period names (rendered exactly as supplied) so
  the report is human-readable.

## What the report MUST NOT include

* Solver internals: variable indices, row indices, raw `x`. They are
  meaningless to the consumer and re-leak the index map.
* Internal-convention quantities. If the model used above-minimum
  dispatch, the report holds actual-MW dispatch only.
* Stale fields from earlier failed attempts. Build the report fresh
  from the validated arrays each solve.
* "Recommended overrides" or repair suggestions unless the prompt asks
  for them. The report is a record of the validated solution, not a
  conversation.
