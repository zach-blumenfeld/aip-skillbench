"""Per command file: parse -> plan -> tune PID -> simulate (RK45) -> metrics -> save.

Requires: Python >= 3.8, numpy, scipy, matplotlib, pyyaml (all in the task image).

Usage (from anywhere):
  python3 run_commands.py --commands /root/commands --params /root/system_params.yaml \
      --out /root/results [--only 001 017] [--budget 40] [--gains gains.json] [--no-tune]

Writes /root/results/<label>/{metrics_3d.json, tuning_results.json,
planned_trajectory.npy, actual_trajectory.npy, plots/*.png} and prints one JSON
summary line per command plus a final table. Exit 1 if any command misses a criterion.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flight_plan_parser import parse_flight_plan  # noqa: E402
from plot_quadrotor import plot_quadrotor  # noqa: E402
from quad_model import load_params, simulate  # noqa: E402
from stepinfo_3d import stepinfo_3d  # noqa: E402
from trajectory_planner import check_accel_limits, num_samples, trajectory_planner  # noqa: E402

# Starting gains (verified on takeoff/hover/land/fly up to ~0.3 rad tilt). Attitude
# Ki stays 0: attitude integral wind-up causes x/y oscillation in z-only maneuvers.
DEFAULT_GAINS = {
    "kp_pos": [20.0, 20.0, 30.0], "ki_pos": [0.0, 0.0, 0.0], "kd_pos": [8.0, 8.0, 10.0],
    "kp_att": [900.0, 900.0, 200.0], "ki_att": [0.0, 0.0, 0.0], "kd_att": [60.0, 60.0, 30.0],
}
# Search coordinates: (key, axes, kind). 'mul' scales the current value, 'add' steps it.
COORDS = [
    ("kp_pos", [0, 1], "mul"), ("kd_pos", [0, 1], "mul"),
    ("kp_pos", [2], "mul"), ("kd_pos", [2], "mul"),
    ("kp_att", [0, 1], "mul"), ("kd_att", [0, 1], "mul"),
    ("ki_pos", [2], "add"), ("ki_pos", [0, 1], "add"),
]
ADD_STEP = {"ki_pos": 1.0}
MUL_BOUNDS = (0.2, 5.0)  # gains stay within these factors of the start gains (robustness)
LIMITS = {"SteadyStateError": 0.05, "Overshoot_pct": 5.0, "max_track_err": 0.05}


def evaluate(params, desired, gains, target, time_vec, integrator, tilt_comp=False):
    actual = simulate(params, desired, gains, integrator, tilt_comp)
    if not np.all(np.isfinite(actual)):
        return None, None, None, float("inf")
    err = np.linalg.norm(actual[0:3] - desired[0:3], axis=0)
    m = stepinfo_3d(actual[0:3], target, time_vec, settling_threshold=0.02)
    track = float(err.max())
    cost = track + 0.5 * m["SteadyStateError"] + 0.002 * m["Overshoot_pct"]
    if track >= LIMITS["max_track_err"] or m["SteadyStateError"] >= LIMITS["SteadyStateError"] \
            or m["Overshoot_pct"] >= LIMITS["Overshoot_pct"]:
        cost += 10.0
    return actual, m, track, cost


def tune(params, desired, target, time_vec, start, budget, tilt_comp=False):
    """Coordinate search with the fast RK4 integrator; returns best gains and cost."""
    best = {k: list(map(float, v)) for k, v in start.items()}
    _, _, _, best_cost = evaluate(params, desired, best, target, time_vec, "rk4", tilt_comp)
    evals, step = 1, 1.5
    while evals < budget and step > 1.05:
        improved = False
        for key, axes, kind in COORDS:
            for direction in (+1, -1):
                if evals >= budget:
                    break
                cand = {k: list(v) for k, v in best.items()}
                for a in axes:
                    if kind == "mul":
                        lo, hi = start[key][a] * MUL_BOUNDS[0], start[key][a] * MUL_BOUNDS[1]
                        cand[key][a] = float(np.clip(cand[key][a] * (step if direction > 0 else 1.0 / step), lo, hi))
                    else:
                        cand[key][a] = max(0.0, cand[key][a] + direction * ADD_STEP[key] * (step - 1.0) * 2)
                if cand == best:
                    continue
                _, _, _, c = evaluate(params, desired, cand, target, time_vec, "rk4", tilt_comp)
                evals += 1
                if c < best_cost * 0.99:
                    best, best_cost, improved = cand, c, True
                    break
        if not improved:
            step = np.sqrt(step)
    return best, best_cost, evals


def run_one(path, params, out_root, budget, start_gains, do_tune, params_path, tilt_comp=False):
    label = os.path.splitext(os.path.basename(path))[0]
    with open(path) as f:
        waypoints, waypoint_times, modes = parse_flight_plan(f.read())
    sr = params["sample_rate"]
    max_iter = num_samples(waypoint_times, sr)
    limits = (params["accel_limit_up"], params["accel_limit_down"], params["accel_limit_horiz"])
    desired = trajectory_planner(waypoints, max_iter, waypoint_times, sr, modes, params["gravity"], limits)
    profiles = trajectory_planner.last_profiles
    out_dir = os.path.join(out_root, label)
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "planned_trajectory.npy"), desired)  # save right after planning
    lim = check_accel_limits(desired, *limits)
    time_vec = waypoint_times[0] + np.arange(max_iter) * params["dt"]
    target = waypoints[0:3, -1]

    def attempt(tilt_comp):
        gains, evals = start_gains, 0
        if do_tune:
            gains, _, evals = tune(params, desired, target, time_vec, start_gains, budget, tilt_comp)
        res = evaluate(params, desired, gains, target, time_vec, "rk45", tilt_comp)
        if do_tune and res[3] >= 10.0:  # tuned gains miss a criterion under RK45: keep the better of tuned/start
            alt = evaluate(params, desired, start_gains, target, time_vec, "rk45", tilt_comp)
            if alt[3] < res[3]:
                gains, res = start_gains, alt
        return (gains, evals, tilt_comp) + tuple(res)

    # Small-angle law first (source design); exact tilt-compensated law only as a retry.
    best = attempt(tilt_comp)
    if best[6] >= 10.0 and not tilt_comp:
        retry = attempt(True)
        if retry[6] < best[6]:
            best = retry
    gains, evals, used_tilt, actual, metrics, track, _ = best
    if actual is None:
        raise RuntimeError(f"{label}: simulation diverged")
    np.save(os.path.join(out_dir, "actual_trajectory.npy"), actual)
    mode = modes[0] if len(set(modes)) == 1 else "+".join(modes)
    with open(os.path.join(out_dir, "metrics_3d.json"), "w") as f:
        json.dump({"mode": mode, **{k: float(v) for k, v in metrics.items()}}, f, indent=2)
    tuning = {k: [float(x) for x in gains[k]] for k in DEFAULT_GAINS}
    with open(os.path.join(out_dir, "tuning_results.json"), "w") as f:
        json.dump(tuning, f, indent=2)
    plot_quadrotor(actual, desired, time_vec, os.path.join(out_dir, "plots"), params_path)
    ok = (lim["ok"] and track < LIMITS["max_track_err"] and metrics["SteadyStateError"] < LIMITS["SteadyStateError"]
          and metrics["Overshoot_pct"] < LIMITS["Overshoot_pct"])
    summary = {"label": label, "mode": mode, "pass": bool(ok), "max_track_err": round(track, 5),
               **{k: round(float(v), 5) for k, v in metrics.items()},
               "accel": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in lim.items()},
               "profiles": profiles, "tilt_comp": used_tilt, "tune_evals": evals}
    print(json.dumps(summary), flush=True)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commands", default="/root/commands")
    ap.add_argument("--params", default="/root/system_params.yaml")
    ap.add_argument("--out", default="/root/results")
    ap.add_argument("--only", nargs="*", help="labels to run, e.g. 001 017")
    ap.add_argument("--budget", type=int, default=40, help="max RK4 evaluations per command in the gain search")
    ap.add_argument("--gains", help="JSON file with starting gains (tuning_results.json schema)")
    ap.add_argument("--no-tune", action="store_true", help="use the starting gains as-is")
    ap.add_argument("--tilt-comp", action="store_true", help="use the exact tilt-compensated law from the start")
    a = ap.parse_args()
    params = load_params(a.params)
    start = DEFAULT_GAINS
    if a.gains:
        with open(a.gains) as f:
            start = {**DEFAULT_GAINS, **json.load(f)}
    files = sorted(glob.glob(os.path.join(a.commands, "*.txt")))
    if a.only:
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in a.only]
    if not files:
        sys.exit(f"No command files found in {a.commands}")
    results = []
    for path in files:
        try:
            results.append(run_one(path, params, a.out, a.budget, start, not a.no_tune, a.params, a.tilt_comp))
        except Exception as e:  # keep going; report at the end
            print(json.dumps({"label": os.path.basename(path), "pass": False, "error": str(e)}), flush=True)
            results.append({"label": os.path.basename(path), "pass": False, "error": str(e)})
    failed = [r["label"] for r in results if not r["pass"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} commands pass all criteria" + (f"; FAILED: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
