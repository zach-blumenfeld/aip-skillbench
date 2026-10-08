"""Closed-loop simulation, gain sweep and per-command result writing.

CLI (from the folder holding these modules):
  python3 simulate.py --params /root/system_params.yaml --commands /root/commands \
      --results /root/results [--tuning tuning_results.json] [--tune]
"""
import argparse
import glob
import itertools
import json
import os
import sys
import time

import numpy as np
from scipy.integrate import solve_ivp

from attitude_controller import attitude_controller, make_attitude_integral
from attitude_planner import attitude_planner
from dynamics import dynamics
from flight_plan_parser import parse_flight_plan
from motor_model import motor_model, prop_matrix
from position_controller import make_position_integral, position_controller
from quad_params import load_params
from stepinfo_3d import stepinfo_3d
from trajectory_planner import (check_accel_limits, max_iter_for, stretch_to_limits,
                                trajectory_planner)

GAIN_KEYS = ["kp_pos", "ki_pos", "kd_pos", "kp_att", "ki_att", "kd_att"]


class State:
    def __init__(self, pos=None, vel=None, rot=None, omega=None, acc=None):
        z = np.zeros(3)
        self.pos = z.copy() if pos is None else np.asarray(pos, float)
        self.vel = z.copy() if vel is None else np.asarray(vel, float)
        self.rot = z.copy() if rot is None else np.asarray(rot, float)
        self.omega = z.copy() if omega is None else np.asarray(omega, float)
        self.acc = z.copy() if acc is None else np.asarray(acc, float)


def _with_gains(params, gains):
    p = dict(params)
    for k in GAIN_KEYS:
        if gains and k in gains:
            p[k] = np.asarray(gains[k], float)
    p["_prop_matrix"] = prop_matrix(p)
    return p


def simulate(waypoints, waypoint_times, modes, params, gains=None, trajectory=None):
    """Return (actual 15xN, desired 15xN, time_vec, trajectory 15xN). The vehicle starts at
    rest on the trajectory's first sample with motors at hover RPM."""
    p = _with_gains(params, gains)
    dt = p["dt"]
    max_iter = max_iter_for(waypoint_times, p["sample_rate"])
    if trajectory is None:
        trajectory = trajectory_planner(waypoints, max_iter, waypoint_times, p["sample_rate"], modes)
    time_vec = waypoint_times[0] + np.arange(max_iter) * dt
    s = np.zeros(16)
    s[0:3] = trajectory[0:3, 0]
    s[8] = trajectory[8, 0]
    s[12:16] = p["hover_rpm"]
    actual = np.zeros((15, max_iter))
    desired = np.zeros((15, max_iter))
    pos_integral = make_position_integral()   # fresh per run: no wind-up across runs
    att_integral = make_attitude_integral()
    for k in range(max_iter):
        cur = State(s[0:3], s[3:6], s[6:9], s[9:12])
        des = State(trajectory[0:3, k], trajectory[3:6, k], trajectory[6:9, k], trajectory[9:12, k], trajectory[12:15, k])
        F, acc_cmd = position_controller(cur, des, p, pos_integral)
        des_ctrl = State(des.pos, des.vel, des.rot, des.omega, acc_cmd)
        des_ctrl.rot, des_ctrl.omega = attitude_planner(des_ctrl, p)
        M = attitude_controller(cur, des_ctrl, p, att_integral)
        F_act, M_act, rpm_dot = motor_model(F, M, s[12:16], p)
        sd = dynamics(p, s, F_act, M_act, rpm_dot)
        actual[:, k] = np.concatenate([s[0:12], sd[3:6]])
        desired[:, k] = np.concatenate([des.pos, des.vel, des_ctrl.rot, des_ctrl.omega, des.acc])
        if k == max_iter - 1:
            break
        sol = solve_ivp(lambda t, y: dynamics(p, y, F_act, M_act, rpm_dot),
                        (time_vec[k], time_vec[k] + dt), s, method="RK45")
        s = sol.y[:, -1]
    return actual, desired, time_vec, trajectory


def tracking_rms(actual, desired):
    return float(np.sqrt(np.mean(np.sum((actual[0:3] - desired[0:3]) ** 2, axis=0))))


def load_commands(commands_dir):
    files = sorted(glob.glob(os.path.join(commands_dir, "*.txt")))
    if not files:
        raise FileNotFoundError(f"no *.txt command files in {commands_dir}")
    return [(os.path.splitext(os.path.basename(f))[0], open(f).read()) for f in files]


def plan_command(text, params, stretch=False):
    waypoints, times, modes = parse_flight_plan(text)
    changes = []
    if stretch:
        times, changes = stretch_to_limits(waypoints, times, modes, params)
    max_iter = max_iter_for(times, params["sample_rate"])
    traj = trajectory_planner(waypoints, max_iter, times, params["sample_rate"], modes)
    return waypoints, times, modes, traj, check_accel_limits(traj, params), changes


def mode_label(modes):
    return modes[0] if len(set(modes)) == 1 else "+".join(modes)


def evaluate_criteria(metrics, criteria):
    """criteria keys (all optional): max_rise_time, max_settling_time, max_overshoot_pct,
    max_steady_state_error, max_tracking_rms. Returns list of failed checks."""
    fails = []
    pairs = [("max_rise_time", "RiseTime"), ("max_settling_time", "SettlingTime"),
             ("max_overshoot_pct", "Overshoot_pct"), ("max_steady_state_error", "SteadyStateError"),
             ("max_tracking_rms", "TrackingRMS")]
    for ck, mk in pairs:
        lim = (criteria or {}).get(ck)
        if lim is not None and mk in metrics and metrics[mk] > float(lim):
            fails.append(f"{mk} {metrics[mk]:.4f} > {lim}")
    return fails


def candidate_gains(grid=None):
    """Critically-damped-ish candidates: pos kp = wn^2, kd = 2*zeta*wn; att kp = wa^2, kd = 2*zeta*wa
    (the attitude law is acceleration-level because it is multiplied by the inertia)."""
    grid = grid or {}
    wn_pos = grid.get("wn_pos", [3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    wn_att = grid.get("wn_att", [16.0, 20.0, 24.0, 28.0])
    zeta = grid.get("zeta", [0.8, 1.0])
    ki_pos_z = grid.get("ki_pos_z", [0.0])
    for wp, wa, z, kiz in itertools.product(wn_pos, wn_att, zeta, ki_pos_z):
        yield {
            "kp_pos": [wp ** 2] * 3, "ki_pos": [0.0, 0.0, kiz], "kd_pos": [2 * z * wp] * 3,
            "kp_att": [wa ** 2, wa ** 2, (wa / 2) ** 2], "ki_att": [0.0, 0.0, 0.0],
            "kd_att": [2 * z * wa, 2 * z * wa, z * wa],
        }


def pick_tuning_set(planned):
    """Shortest command per mode plus the most aggressive (highest peak accel) command."""
    by_mode = {}
    for item in planned:
        m = item["mode"]
        if m not in by_mode or item["duration"] < by_mode[m]["duration"]:
            by_mode[m] = item
    chosen = {i["label"]: i for i in by_mode.values()}
    hard = max(planned, key=lambda i: max(i["check"]["peak_up"], -i["check"]["peak_down"], i["check"]["peak_horiz"]))
    chosen[hard["label"]] = hard
    return list(chosen.values())


def tune(planned, params, criteria=None, grid=None, cost_tolerance=0.10, log=sys.stderr):
    """Sweep candidate gains over a representative subset; return tuning_results dict.

    Selection: fewest criteria failures, then -- among candidates within `cost_tolerance`
    of the best cost -- the lowest position bandwidth (the raw optimum sits next to
    unstable gain sets; the slower loop keeps margin on commands outside the subset)."""
    subset = pick_tuning_set(planned)
    best, rows = None, []
    for gains in candidate_gains(grid):
        cost, n_fail, worst = 0.0, 0, {}
        for item in subset:
            act, des, tv, _ = simulate(item["waypoints"], item["times"], item["modes"], params, gains, item["traj"])
            met = stepinfo_3d(act[0:3], item["waypoints"][0:3, -1], tv)
            met["TrackingRMS"] = tracking_rms(act, des)
            n_fail += len(evaluate_criteria(met, criteria))
            d0 = max(np.linalg.norm(item["waypoints"][0:3, -1] - item["waypoints"][0:3, 0]), 1e-6)
            # Normalised: final error, tracking error, overshoot (all relative to move size)
            cost += met["SteadyStateError"] / d0 + met["TrackingRMS"] / d0 + 0.01 * met["Overshoot_pct"] \
                + (10.0 if not np.all(np.isfinite(act)) else 0.0)
            worst[item["label"]] = {k: round(v, 5) for k, v in met.items()}
        row = {"gains": gains, "cost": cost, "criteria_failures": n_fail, "metrics": worst}
        rows.append(row)
        print(f"wn_pos={np.sqrt(gains['kp_pos'][0]):.1f} wn_att={np.sqrt(gains['kp_att'][0]):.1f} "
              f"zeta={gains['kd_pos'][0] / (2 * np.sqrt(gains['kp_pos'][0])):.2f} "
              f"cost={cost:.4f} fails={n_fail}", file=log)
    min_fail = min(r["criteria_failures"] for r in rows)
    ok = [r for r in rows if r["criteria_failures"] == min_fail]
    best_cost = min(r["cost"] for r in ok)
    near = [r for r in ok if r["cost"] <= best_cost * (1 + cost_tolerance)]
    best = min(near, key=lambda r: (r["gains"]["kp_pos"][2], r["cost"]))
    return {
        **{k: [float(v) for v in best["gains"][k]] for k in GAIN_KEYS},
        "cost": best["cost"],
        "criteria_failures": best["criteria_failures"],
        "tuning_commands": [i["label"] for i in subset],
        "tuning_metrics": best["metrics"],
        "candidates_evaluated": len(rows),
        "sweep": [{"kp_pos": r["gains"]["kp_pos"], "kd_pos": r["gains"]["kd_pos"], "kp_att": r["gains"]["kp_att"],
                   "kd_att": r["gains"]["kd_att"], "cost": r["cost"], "criteria_failures": r["criteria_failures"]}
                  for r in rows],
    }


def plan_all(commands_dir, params, stretch=False):
    planned = []
    for label, text in load_commands(commands_dir):
        wp, times, modes, traj, check, changes = plan_command(text, params, stretch)
        planned.append({"label": label, "text": text.strip(), "waypoints": wp, "times": times, "modes": modes,
                        "mode": mode_label(modes), "traj": traj, "check": check, "stretched": changes,
                        "duration": float(times[-1] - times[0])})
    return planned


def run_all(planned, params, tuning_results, results_dir, criteria=None, params_path=None, plots=True, log=sys.stderr):
    """Simulate every command and write results_dir/<label>/{planned_trajectory.npy,
    metrics_3d.json, tuning_results.json, plots/}. Returns a per-command summary list."""
    from plot_quadrotor import plot_quadrotor
    gains = {k: tuning_results[k] for k in GAIN_KEYS}
    summary = []
    for item in planned:
        t0 = time.time()
        out_dir = os.path.join(results_dir, item["label"])
        os.makedirs(out_dir, exist_ok=True)
        np.save(os.path.join(out_dir, "planned_trajectory.npy"), item["traj"])  # saved right after planning
        act, des, tv, _ = simulate(item["waypoints"], item["times"], item["modes"], params, gains, item["traj"])
        metrics = stepinfo_3d(act[0:3, :], item["waypoints"][0:3, -1], tv)
        with open(os.path.join(out_dir, "metrics_3d.json"), "w") as f:
            json.dump({"mode": item["mode"], **metrics}, f, indent=2)
        with open(os.path.join(out_dir, "tuning_results.json"), "w") as f:
            json.dump(tuning_results, f, indent=2)
        if plots:
            plot_quadrotor(act, des, tv, save_dir=os.path.join(out_dir, "plots"), params_path=params_path)
        check = check_accel_limits(np.load(os.path.join(out_dir, "planned_trajectory.npy")), params)
        full = dict(metrics, TrackingRMS=tracking_rms(act, des))
        fails = evaluate_criteria(full, criteria) + check["violations"]
        if not np.all(np.isfinite(act)):
            fails.append("simulation diverged (non-finite state)")
        summary.append({"label": item["label"], "command": item["text"], "mode": item["mode"],
                        "metrics": {k: round(v, 5) for k, v in full.items()},
                        "max_abs_xy_error": round(float(np.abs(act[0:2] - des[0:2]).max()), 5),
                        "accel_ok": check["ok"], "stretched": item["stretched"], "failures": fails,
                        "out_dir": out_dir})
        print(f"{item['label']} {item['mode']}: {metrics} ({time.time() - t0:.1f}s)", file=log)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="/root/system_params.yaml")
    ap.add_argument("--commands", default="/root/commands")
    ap.add_argument("--results", default="/root/results")
    ap.add_argument("--tuning", help="tuning_results.json to reuse instead of sweeping")
    ap.add_argument("--stretch", action="store_true", help="lengthen segments that exceed accel limits")
    a = ap.parse_args()
    params = load_params(a.params)
    planned = plan_all(a.commands, params, a.stretch)
    tuning = json.load(open(a.tuning)) if a.tuning else tune(planned, params)
    summary = run_all(planned, params, tuning, a.results, params_path=a.params)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
