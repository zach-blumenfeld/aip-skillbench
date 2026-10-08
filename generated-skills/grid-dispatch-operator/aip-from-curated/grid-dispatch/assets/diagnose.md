The dispatch solve for {meta.name} did not reach an optimal solution.

Task request:
{task_request}

Solver status: {solver_status}
Errors: {solver_errors}
Diagnostics: {diagnostics}
Notes: {notes}

Work out why, using the diagnostics and the network file (json.load, not line paging):
- error / exception: a malformed or unexpected file (missing key, a bus number in gen or
  branch rows that is not in bus, unsupported gencost). Fix the cause (e.g. correct
  network_path) and re-run `scripts/solve_dispatch.py --network <file> --out <path>`.
- infeasible: compare load_MW with sum_pmin_MW..sum_pmax_MW, reserve_requirement_MW with
  sum_reserve_capacity_MW and with spare capacity (sum_pmax − load), and suspect line limits
  when only the network-constrained solve fails (re-run with `--copper-plate` to confirm).
  Do not silently drop a constraint the task requires; report which constraint makes the
  problem infeasible and by how much.
Produce `final_answer`: what failed, the evidence, and any output written.
