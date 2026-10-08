# Diagnose a failed solve

The solver did not reach an optimal solution.

Summary / error: {solve_summary}
Network summary: {network_summary}
Inspector issues: {issues}  warnings: {warnings}
Inputs: network_path={network_path}, counterfactual={counterfactual}, output_path={output_path}

Work out why, in this order:

1. `error` mentions venv / pip: the container could not install numpy, scipy, cvxpy. Check network
   access, or whether another interpreter already has them (`python3 -c "import cvxpy"`), then re-run
   `scripts/solve_market.py` yourself with the same state on stdin (set `DCOPF_VENV` to a writable path).
2. A traceback: fix the input that caused it (bus number not in network, malformed modification) and
   re-run the script the same way.
3. Status `infeasible`: compare total load with in-service Pmax/Pmin and reserve capacity with the
   requirement in the network summary; a counterfactual that tightens a limit or raises load can
   make the problem infeasible. Report which constraint set is responsible; do not relax constraints
   the request did not ask to relax.
4. Status `unbounded` or `inaccurate`: check for zero-reactance or islanded branches and an unsupported
   cost model (NCOST > 3, negative quadratic term).

If a re-run succeeds, write the report exactly as the write-report instructions describe (draft at
`report_draft.json` next to the results file). Post `output_path` (the report file, or "" if none)
and `final_answer` (what failed, why, and what was or was not produced).
