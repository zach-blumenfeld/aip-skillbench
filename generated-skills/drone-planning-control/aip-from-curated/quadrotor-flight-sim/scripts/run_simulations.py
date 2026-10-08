"""Simulate every command with tuning_results and write results_dir/<label>/:
planned_trajectory.npy, metrics_3d.json, tuning_results.json, plots/*.png. Re-checks the
saved trajectories against the acceleration limits and the success criteria."""
import os

from stepio import emit, fail, read_input, use_lib

state, _ = read_input()
lib = use_lib(state.get("workdir"))
os.environ["QUAD_PARAMS"] = state["params_path"]
from quad_params import load_params  # noqa: E402
from simulate import GAIN_KEYS, plan_all, run_all  # noqa: E402

tuning = state.get("tuning_results") or {}
missing = [k for k in GAIN_KEYS if k not in tuning]
if missing:
    fail(f"tuning_results is missing gain arrays: {missing}")
try:
    params = load_params(state["params_path"])
    planned = plan_all(state["commands_dir"], params, stretch=bool(state.get("stretch_infeasible")))
    summary = run_all(planned, params, tuning, state["results_dir"], criteria=state.get("success_criteria") or {},
                      params_path=state["params_path"])
except Exception as e:
    fail(f"{type(e).__name__}: {e}")

expected = ["planned_trajectory.npy", "metrics_3d.json", "tuning_results.json",
            "plots/desired_vs_actual.png", "plots/errors.png", "plots/cumulative_errors.png"]
for row in summary:
    row["missing_files"] = [f for f in expected if not os.path.isfile(os.path.join(row["out_dir"], f))]
    row["failures"] += [f"missing {f}" for f in row["missing_files"]]
failures = [{"label": r["label"], "mode": r["mode"], "failures": r["failures"], "metrics": r["metrics"]}
            for r in summary if r["failures"]]
emit({
    "results": summary,
    "failures": failures,
    "all_pass": not failures or bool(state.get("accept_failures")),
    "simulator_lib": lib,
})
