The DC-OPF with reserves for `{network_path}` did not produce an optimal dispatch.

Solver status: {solve_status}
Most likely cause (from the diagnose step): {infeasibility_cause}

Pre-solve diagnostics (counts, MW totals, feasibility checks, solver attempts):

{diagnostics}

Write a short infeasibility report for the operator:

1. State which constraint family makes the problem infeasible (or that the solver
   failed), quoting the MW figures from the diagnostics that prove it.
2. If the cause is network congestion or unclear, confirm it: load the network with
   Python's `json.load` (never page the file), relax RATE_A or the reserve requirement in
   a copy outside the skill folder, and re-solve the copy with the skill's solver:
   pipe a JSON object whose `state` holds `network_path` (the copy) into
   `python3 <skill folder>/scripts/dispatch.py solve`; it prints `solve_status`.
   Narrow it down: drop all limits first, then only the limits on branches touching the
   suspect buses. Report what relaxation makes it solvable.
3. For data errors, name the table, row, and field from `data_errors`.
4. Say what data change or operator action would restore feasibility.

Do not write report.json with a made-up or copper-plate dispatch: the report must come
from a feasible DC-OPF solve.
