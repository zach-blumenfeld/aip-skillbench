"""Sweep PID gains on a representative subset of the commands (shortest per mode + the most
aggressive) and return the selected gains as tuning_results."""
import json
import os

from stepio import emit, fail, read_input, use_lib

state, _ = read_input()
lib = use_lib(state.get("workdir"))
os.environ["QUAD_PARAMS"] = state["params_path"]
from quad_params import load_params  # noqa: E402
from simulate import plan_all, tune  # noqa: E402

try:
    params = load_params(state["params_path"])
    planned = plan_all(state["commands_dir"], params, stretch=bool(state.get("stretch_infeasible")))
    grid = state.get("tuning_grid") or None
    results = tune(planned, params, criteria=state.get("success_criteria") or {}, grid=grid)
except Exception as e:
    fail(f"{type(e).__name__}: {e}")

sweep = results.pop("sweep")
best5 = sorted(sweep, key=lambda r: (r["criteria_failures"], r["cost"]))[:5]
emit({"tuning_results": results, "tuning_top_candidates": best5, "simulator_lib": lib})
