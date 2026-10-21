"""Quadrotor command-flight library: parser, planner, motor model, dynamics,
position/attitude PID, 3D step metrics, plots, gain tuning, and per-command runner.

Imported by run_all.py and rerun_failed.py (same folder). Works with
numpy>=1.26, scipy>=1.13, matplotlib>=3.8, pyyaml.
"""
import json
import math
import os
import re

import numpy as np
import yaml
from scipy.integrate import solve_ivp

# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------

def load_params(path):
    with open(path) as f:
        p = yaml.safe_load(f)
    p = dict(p)
    p["inertia"] = np.diag(np.asarray(p["inertia"], dtype=float))  # diagonal -> matrix
    for k in ("sample_rate", "mass", "gravity", "arm_length", "thrust_coefficient",
              "moment_scale", "motor_constant", "rpm_min", "rpm_max"):
        p[k] = float(p[k])
    t_max = 4 * p["thrust_coefficient"] * p["rpm_max"] ** 2
    t_min = 4 * p["thrust_coefficient"] * p["rpm_min"] ** 2
    mg = p["mass"] * p["gravity"]
    # Prefer the file's limits; derive from motor limits when absent.
    p.setdefault("accel_limit_up", (t_max - mg) / p["mass"])
    p.setdefault("accel_limit_down", (mg - t_min) / p["mass"])
    p.setdefault("accel_limit_horiz", math.sqrt(max(t_max ** 2 - mg ** 2, 0.0)) / p["mass"])
    for k in ("accel_limit_up", "accel_limit_down", "accel_limit_horiz"):
        p[k] = float(p[k])
    p["dt"] = 1.0 / p["sample_rate"]
    return p


# --------------------------------------------------------------------------
# Flight plan parser
# --------------------------------------------------------------------------

_NUM = r"([-+]?\d*\.?\d+)"
_UNIT_M = r"\s*m(?:eters?|etres?)?\b"
_UNIT_S = r"\s*s(?:ec(?:ond)?s?)?\b"
_TRIPLE = r"\(\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*\)"
PATTERNS = {
    "takeoff": re.compile(r"take[\s-]*off\s+to\s+" + _NUM + _UNIT_M + r"(?:\s+(?:height|altitude))?\s+in\s+" + _NUM + _UNIT_S, re.I),
    "hover": re.compile(r"hover\s+at\s+" + _NUM + _UNIT_M + r"(?:\s+(?:height|altitude))?\s+for\s+" + _NUM + _UNIT_S, re.I),
    "land": re.compile(r"land\s+from\s+" + _NUM + _UNIT_M + r"(?:\s+(?:height|altitude))?\s+in\s+" + _NUM + _UNIT_S, re.I),
    "fly": re.compile(r"fly\s+from\s*" + _TRIPLE + r"\s*to\s*" + _TRIPLE + r"\s+in\s+" + _NUM + _UNIT_S, re.I),
}


class FlightPlanParser:
    """Stateful parser: accumulates end waypoints [x, y, z, yaw], arrival times, modes."""

    def __init__(self):
        self.pos = [0.0, 0.0, 0.0, 0.0]
        self.t = 0.0
        self.waypoints, self.times, self.modes = [], [], []

    def _start(self, start_pos):
        # First command: the start waypoint is where the command says the drone is
        # (ground for takeoff, h for hover/land, the 'from' point for fly).
        if not self.waypoints:
            self.pos = list(start_pos)
            self.waypoints.append(list(self.pos))
            self.times.append(0.0)

    def _push(self, end_pos, duration, mode):
        if duration <= 0:
            raise ValueError("duration must be > 0")
        self.t += duration
        self.pos = list(end_pos)
        self.waypoints.append(list(self.pos))  # copy: never share the list
        self.times.append(self.t)
        self.modes.append(mode)

    def feed(self, line):
        line = line.strip()
        if not line:
            return True
        m = PATTERNS["fly"].search(line)
        if m:
            v = [float(g) for g in m.groups()]
            self._start([v[0], v[1], v[2], 0.0])
            self._push([v[3], v[4], v[5], self.pos[3]], v[6], "fly")
            return True
        for mode in ("takeoff", "hover", "land"):
            m = PATTERNS[mode].search(line)
            if not m:
                continue
            h, dur = float(m.group(1)), float(m.group(2))
            x, y, yaw = (self.pos[0], self.pos[1], self.pos[3]) if self.waypoints else (0.0, 0.0, 0.0)
            if mode == "takeoff":
                self._start([x, y, 0.0, yaw])
                self._push([self.pos[0], self.pos[1], h, yaw], dur, mode)
            elif mode == "hover":
                self._start([x, y, h, yaw])
                self._push([self.pos[0], self.pos[1], h, yaw], dur, mode)
            else:
                self._start([x, y, h, yaw])
                self._push([self.pos[0], self.pos[1], 0.0, yaw], dur, mode)
            return True
        return False

    def result(self):
        return np.array(self.waypoints, dtype=float).T, np.array(self.times, dtype=float), list(self.modes)


def parse_flight_plan(text):
    """Return (waypoints 4xn, waypoint_times n, modes n-1, unparsed_lines)."""
    p = FlightPlanParser()
    bad = [ln.strip() for ln in text.splitlines() if not p.feed(ln)]
    if not p.waypoints:
        return None, None, [], bad or [text.strip()]
    wp, t, modes = p.result()
    return wp, t, modes, bad


# --------------------------------------------------------------------------
# Trajectory planner
# --------------------------------------------------------------------------

def _segment_profile(T, s_acc_max):
    """Return (kind, f(tau)->(s, sd, sdd)) for one segment of duration T.

    Default is the quintic (minimum-jerk) spline: zero velocity AND acceleration at
    both ends, peak |s''| = 5.774/T^2. A clamped cubic (zero end velocities only)
    starts with an acceleration step the drone cannot follow instantly, which
    roughly doubles the tracking error on fast moves. If the quintic breaks the
    acceleration limit, fall back to a trapezoidal velocity profile (needs
    s_acc_max >= 4/T^2) whose acceleration sits 30 % of the way from the minimum
    4/T^2 to the limit, leaving thrust headroom for the feedback loop.
    """
    if 5.7735 / T ** 2 <= s_acc_max:
        def quintic(tau):
            u = tau / T
            return (10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5,
                    (30 * u ** 2 - 60 * u ** 3 + 30 * u ** 4) / T,
                    (60 * u - 180 * u ** 2 + 120 * u ** 3) / T ** 2)
        return "quintic", quintic
    if 4.0 / T ** 2 > s_acc_max:
        return "infeasible", None
    a = 4.0 / T ** 2 + 0.3 * (s_acc_max - 4.0 / T ** 2)
    ta = (T - math.sqrt(T ** 2 - 4.0 / a)) / 2.0
    v = a * ta

    def trap(tau):
        if tau < ta:
            return 0.5 * a * tau ** 2, a * tau, a
        if tau <= T - ta:
            return 0.5 * a * ta ** 2 + v * (tau - ta), v, 0.0
        r = T - tau
        return 1.0 - 0.5 * a * r ** 2, a * r, -a
    return "trapezoid", trap


def trajectory_planner(waypoints, max_iter, waypoint_times, sample_rate, modes, params, margin=0.98):
    """(15 x max_iter) desired state: pos, vel, [phi, theta, psi], [p, q, r], acc.

    Returns (trajectory_state, info) where info lists the profile per segment and
    whether every segment fits inside the acceleration limits.
    """
    dt = 1.0 / sample_rate
    traj = np.zeros((15, max_iter))
    seg_info, feasible = [], True
    profiles = []
    for i, mode in enumerate(modes):
        p0, p1 = waypoints[:3, i], waypoints[:3, i + 1]
        t0, t1 = waypoint_times[i], waypoint_times[i + 1]
        T = t1 - t0
        d = p1 - p0
        dh, dz = math.hypot(d[0], d[1]), abs(d[2])
        lim = []
        if dz > 1e-12:
            lim.append(min(params["accel_limit_up"], params["accel_limit_down"]) / dz)
        if dh > 1e-12:
            lim.append(params["accel_limit_horiz"] / dh)
        s_max = margin * min(lim) if lim else float("inf")
        if mode == "hover" or (dz <= 1e-12 and dh <= 1e-12):
            kind, f = "hold", (lambda tau: (0.0, 0.0, 0.0))
        else:
            kind, f = _segment_profile(T, s_max)
            if f is None:
                feasible = False
                kind, f = "quintic-over-limit", _segment_profile(T, float("inf"))[1]
        seg_info.append({"mode": mode, "profile": kind, "duration": T,
                         "min_feasible_duration": (2.0 / math.sqrt(s_max / margin)) if lim else 0.0})
        profiles.append((t0, t1, p0, d, waypoints[3, i], waypoints[3, i + 1], f))

    for k in range(max_iter):
        t = k * dt
        idx = len(profiles) - 1
        for j, pr in enumerate(profiles):
            if t <= pr[1] + 1e-12:
                idx = j
                break
        t0, t1, p0, d, y0, y1, f = profiles[idx]
        tau = min(max(t - t0, 0.0), t1 - t0)
        s, sd, sdd = f(tau)
        pos, vel, acc = p0 + s * d, sd * d, sdd * d
        # yaw: clamped cubic between segment yaw endpoints
        T = t1 - t0
        u = tau / T
        yaw = y0 + (y1 - y0) * (3 * u ** 2 - 2 * u ** 3)
        yaw_rate = (y1 - y0) * (6 * u - 6 * u ** 2) / T
        rot, omega = attitude_planner(acc, yaw, yaw_rate, params)
        traj[0:3, k], traj[3:6, k], traj[12:15, k] = pos, vel, acc
        traj[6:9, k] = rot
        traj[9:12, k] = omega
    return traj, {"segments": seg_info, "feasible": feasible}


def check_accel_limits(traj, params, tol=1e-9):
    a = traj[12:15]
    up = float(a[2].max())
    down = float(-a[2].min())
    horiz = float(np.hypot(a[0], a[1]).max())
    ok = (up <= params["accel_limit_up"] + tol and down <= params["accel_limit_down"] + tol
          and horiz <= params["accel_limit_horiz"] + tol)
    return ok, {"max_up": up, "max_down": down, "max_horiz": horiz}


# --------------------------------------------------------------------------
# Motor model + dynamics
# --------------------------------------------------------------------------

def prop_matrix(params):
    cT, cQ, d = params["thrust_coefficient"], params["moment_scale"], params["arm_length"]
    return np.array([
        [cT, cT, cT, cT],
        [0.0, d * cT, 0.0, -d * cT],
        [-d * cT, 0.0, d * cT, 0.0],
        [-cQ, cQ, -cQ, cQ],
    ])


def motor_model(F, M, motor_rpm, params, P=None, P_inv=None):
    P = prop_matrix(params) if P is None else P
    P_inv = np.linalg.inv(P) if P_inv is None else P_inv
    rpm_sq = P_inv @ np.array([F, M[0], M[1], M[2]])
    rpm_des = np.clip(np.sqrt(np.maximum(rpm_sq, 0.0)), params["rpm_min"], params["rpm_max"])
    rpm_dot = params["motor_constant"] * (rpm_des - motor_rpm)
    fm = P @ (motor_rpm ** 2)
    return fm[0], fm[1:4], rpm_dot


def dynamics(params, s, F, M, rpm_dot, I_inv=None):
    m, g = params["mass"], params["gravity"]
    phi, theta, psi = s[6], s[7], s[8]
    cphi, sphi, cth, sth, cps, sps = (math.cos(phi), math.sin(phi), math.cos(theta),
                                      math.sin(theta), math.cos(psi), math.sin(psi))
    a = F / m
    ds = np.empty(16)
    ds[0:3] = s[3:6]
    ds[3] = a * (cphi * sth * cps + sphi * sps)
    ds[4] = a * (cphi * sth * sps - sphi * cps)
    ds[5] = -g + a * cphi * cth
    ds[6:9] = s[9:12]
    I_inv = np.linalg.inv(params["inertia"]) if I_inv is None else I_inv
    ds[9:12] = I_inv @ M
    ds[12:16] = rpm_dot
    return ds


# --------------------------------------------------------------------------
# Controllers
# --------------------------------------------------------------------------

def make_position_integral():
    return {"e": np.zeros(3)}


def make_attitude_integral():
    return {"e": np.zeros(3)}


def position_controller(state, des, gains, params, integral):
    pos_err = state[0:3] - des[0:3]
    vel_err = state[3:6] - des[3:6]
    integral["e"] += pos_err * params["dt"]
    acc = des[12:15] - gains["kp_pos"] * pos_err - gains["ki_pos"] * integral["e"] - gains["kd_pos"] * vel_err
    # Full thrust magnitude m*|acc + g e3|. The small-angle m*(g + acc_z) loses
    # altitude whenever the drone tilts (3-8x larger errors on diagonal flights).
    F = params["mass"] * math.sqrt(acc[0] ** 2 + acc[1] ** 2 + (params["gravity"] + acc[2]) ** 2)
    return F, acc


def attitude_planner(acc, yaw_des, yaw_rate_des, params):
    """Desired [phi, theta, psi] that points thrust along acc + g e3 (ZYX Euler).
    For small tilts this reduces to phi ~ (ax sin psi - ay cos psi)/g,
    theta ~ (ax cos psi + ay sin psi)/g."""
    az = params["gravity"] + acc[2]
    a_fwd = acc[0] * math.cos(yaw_des) + acc[1] * math.sin(yaw_des)
    a_side = acc[0] * math.sin(yaw_des) - acc[1] * math.cos(yaw_des)
    theta = math.atan2(a_fwd, az)
    phi = math.atan2(a_side * math.cos(theta), az)
    return np.array([phi, theta, yaw_des]), np.array([0.0, 0.0, yaw_rate_des])


def attitude_controller(state, rot_des, omega_des, gains, params, integral):
    e = rot_des - state[6:9]
    integral["e"] += e * params["dt"]
    # gains element-wise, then the inertia matrix product
    return params["inertia"] @ (gains["kp_att"] * e + gains["ki_att"] * integral["e"]
                                + gains["kd_att"] * (omega_des - state[9:12]))


# --------------------------------------------------------------------------
# Closed-loop simulation
# --------------------------------------------------------------------------

def hover_rpm(params):
    return math.sqrt(params["mass"] * params["gravity"] / (4 * params["thrust_coefficient"]))


def simulate(traj, gains, params):
    """Run the closed loop along traj; each control step is integrated with
    solve_ivp RK45 over [t_k, t_k+1] with F, M, rpm_dot held constant."""
    n = traj.shape[1]
    dt = params["dt"]
    P = prop_matrix(params)
    P_inv = np.linalg.inv(P)
    I_inv = np.linalg.inv(params["inertia"])
    gains = {k: np.asarray(v, dtype=float) for k, v in gains.items()}
    s = np.zeros(16)
    s[0:3] = traj[0:3, 0]
    s[3:6] = traj[3:6, 0]
    s[8] = traj[8, 0]
    s[12:16] = hover_rpm(params)
    actual = np.zeros((15, n))
    actual[0:12, 0] = s[0:12]
    actual[12:15, 0] = 0.0
    pos_int, att_int = make_position_integral(), make_attitude_integral()
    for k in range(n - 1):
        des = traj[:, k]
        F, acc = position_controller(s, des, gains, params, pos_int)
        rot_des, omega_des = attitude_planner(acc, des[8], des[11], params)
        M = attitude_controller(s, rot_des, omega_des, gains, params, att_int)
        F_a, M_a, rpm_dot = motor_model(F, M, s[12:16], params, P, P_inv)
        f = lambda _t, y: dynamics(params, y, F_a, M_a, rpm_dot, I_inv)
        sol = solve_ivp(f, (k * dt, (k + 1) * dt), s, method="RK45")
        s = sol.y[:, -1]
        if not np.all(np.isfinite(s)):
            actual[:, k + 1:] = np.nan
            break
        actual[0:12, k + 1] = s[0:12]
        actual[12:15, k + 1] = dynamics(params, s, F_a, M_a, rpm_dot, I_inv)[3:6]
    return actual


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def stepinfo_3d(pos_actual, pos_target, t, settling_threshold=0.02):
    dist = np.linalg.norm(pos_actual - np.asarray(pos_target).reshape(3, 1), axis=0)
    d0 = dist[0]
    zero = {"RiseTime": 0.0, "SettlingTime": 0.0, "Overshoot_pct": 0.0, "SteadyStateError": 0.0}
    if d0 < 1e-6:
        return zero
    rise = next((float(t[k]) for k in range(len(dist)) if dist[k] <= 0.1 * d0), float(t[-1]))
    band = settling_threshold * d0
    above = np.nonzero(dist > band)[0]
    settling = float(t[above[-1]]) if len(above) else 0.0
    inside = np.nonzero(dist <= band)[0]
    overshoot = float(dist[inside[0]:].max() / d0 * 100.0) if len(inside) else 0.0
    return {"RiseTime": rise, "SettlingTime": settling, "Overshoot_pct": overshoot,
            "SteadyStateError": float(dist[-1])}


def evaluate(actual, traj, waypoints, params, settling_threshold=0.02):
    n = traj.shape[1]
    t = np.arange(n) * params["dt"]
    if not np.all(np.isfinite(actual)):
        return None, float("inf"), False
    metrics = stepinfo_3d(actual[0:3], waypoints[0:3, -1], t, settling_threshold)
    max_err = float(np.linalg.norm(actual[0:3] - traj[0:3], axis=0).max())
    return metrics, max_err, True


def criteria(metrics, max_err, accel_ok):
    if metrics is None:
        return {"steady_state": False, "overshoot": False, "accel_limits": accel_ok, "tracking": False}
    return {"steady_state": metrics["SteadyStateError"] < 0.05,
            "overshoot": metrics["Overshoot_pct"] < 5.0,
            "accel_limits": bool(accel_ok),
            "tracking": max_err < 0.05}


# --------------------------------------------------------------------------
# Tuning
# --------------------------------------------------------------------------

BASE_GAINS = {
    "kp_pos": [12.0, 12.0, 16.0], "ki_pos": [0.0, 0.0, 0.0], "kd_pos": [7.0, 7.0, 8.0],
    "kp_att": [400.0, 400.0, 100.0], "ki_att": [0.0, 0.0, 0.0], "kd_att": [40.0, 40.0, 20.0],
}


def candidate_gains(base=None, wide=False):
    """Grid around base: position-loop stiffness x damping x attitude stiffness.
    The base itself is always the first candidate."""
    base = base or BASE_GAINS
    sps = (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0) if wide else (1.0, 2.0, 3.0)
    sds = (0.5, 0.75, 1.0, 1.4, 2.0) if wide else (0.75, 1.0, 1.4)
    sas = (0.5, 0.75, 1.0, 1.5, 2.0) if wide else (0.75, 1.5)
    out = [{k: list(map(float, v)) for k, v in base.items()}]
    for sp in sps:
        for sd in sds:
            for sa in sas:
                g = {k: list(map(float, v)) for k, v in base.items()}
                g["kp_pos"] = [v * sp for v in base["kp_pos"]]
                g["kd_pos"] = [v * sd * math.sqrt(sp) for v in base["kd_pos"]]
                g["kp_att"] = [v * sa for v in base["kp_att"]]
                g["kd_att"] = [v * math.sqrt(sa) for v in base["kd_att"]]
                out.append(g)
    return out


def _score(metrics, max_err, ok):
    if not ok or metrics is None:
        return (1, float("inf"))
    passes = metrics["SteadyStateError"] < 0.05 and metrics["Overshoot_pct"] < 5.0 and max_err < 0.05
    return (0 if passes else 1, max_err + 0.01 * metrics["Overshoot_pct"] / 5.0 + metrics["SteadyStateError"])


def tune(traj, waypoints, params, candidates):
    """Simulate every candidate; return (score, gains, actual, metrics, max_err) of the best.
    Score: passing all criteria first, then smallest max tracking error."""
    best = None
    for g in candidates:
        act = simulate(traj, g, params)
        m, e, ok = evaluate(act, traj, waypoints, params)
        sc = _score(m, e, ok)
        if best is None or sc < best[0]:
            best = (sc, g, act, m, e)
    return best


# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------

def plot_quadrotor(state, state_des, time_vec, save_dir, time_step):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    groups = [("Position", 0, ["x", "y", "z"], "m"),
              ("Velocity", 3, ["vx", "vy", "vz"], "m/s"),
              ("Orientation", 6, [r"$\phi$", r"$\theta$", r"$\psi$"], "rad"),
              ("Angular velocity", 9, ["p", "q", "r"], "rad/s"),
              ("Acceleration", 12, ["ax", "ay", "az"], "m/s$^2$")]
    os.makedirs(save_dir, exist_ok=True)
    figs = {name: plt.subplots(5, 3, figsize=(16, 20)) for name in ("desired_vs_actual", "errors", "cumulative_errors")}
    for gi, (title, r0, labels, unit) in enumerate(groups):
        for j in range(3):
            act, des = state[r0 + j], state_des[r0 + j]
            err = act - des
            cum = time_step * np.cumsum(np.abs(err))
            ax = figs["desired_vs_actual"][1][gi, j]
            ax.plot(time_vec, des, "b-", label="desired")
            ax.plot(time_vec, act, "r--", label="actual")
            ax.set_title(f"{title}: {labels[j]}")
            ax.set_ylabel(unit)
            if gi == 0 and j == 0:
                ax.legend()
            ax = figs["errors"][1][gi, j]
            ax.plot(time_vec, err, "k-")
            ax.set_title(f"{title} error: {labels[j]}")
            ax.set_ylabel(unit)
            ax = figs["cumulative_errors"][1][gi, j]
            ax.plot(time_vec, cum, "m-")
            ax.set_title(f"{title} cumulative |error|: {labels[j]}")
            ax.set_ylabel(f"{unit}·s")
    for name, (fig, axes) in figs.items():
        for ax in axes[-1]:
            ax.set_xlabel("time [s]")
        fig.tight_layout()
        fig.savefig(os.path.join(save_dir, f"{name}.png"))
        plt.close(fig)


# --------------------------------------------------------------------------
# Per-command runner
# --------------------------------------------------------------------------

def run_command(label, text, params, results_dir, candidates=None):
    """Parse, plan, tune, simulate (RK45), and write every output for one command."""
    rec = {"label": label, "command": text.strip()}
    wp, wt, modes, bad = parse_flight_plan(text)
    if wp is None or bad:
        rec.update({"status": "unparsed", "unparsed_lines": bad, "pass": False})
        return rec
    fs = params["sample_rate"]
    time_final = float(wt[-1])
    max_iter = int(round(time_final * fs)) + 1
    traj, info = trajectory_planner(wp, max_iter, wt, fs, modes, params)
    accel_ok, accel = check_accel_limits(traj, params)
    out_dir = os.path.join(results_dir, label)
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "planned_trajectory.npy"), traj)
    rec.update({"mode": modes[-1], "modes": modes, "duration": time_final,
                "profiles": [s["profile"] for s in info["segments"]],
                "min_feasible_durations": [round(s["min_feasible_duration"], 3) for s in info["segments"]],
                "plan_feasible": info["feasible"], "accel": accel})

    _, gains, actual, metrics, max_err = tune(traj, wp, params, candidates or candidate_gains())
    crit = criteria(metrics, max_err, accel_ok)
    if metrics is None:  # every candidate diverged
        metrics = {"RiseTime": None, "SettlingTime": None, "Overshoot_pct": None, "SteadyStateError": None}
    np.save(os.path.join(out_dir, "actual_trajectory.npy"), actual)
    with open(os.path.join(out_dir, "metrics_3d.json"), "w") as f:
        json.dump({"mode": modes[-1], **metrics}, f, indent=2)
    tuning = {k: [float(v) for v in gains[k]] for k in ("kp_pos", "ki_pos", "kd_pos", "kp_att", "ki_att", "kd_att")}
    with open(os.path.join(out_dir, "tuning_results.json"), "w") as f:
        json.dump(tuning, f, indent=2)
    if np.all(np.isfinite(actual)):
        plot_quadrotor(actual, traj, np.arange(max_iter) / fs, os.path.join(out_dir, "plots"), params["dt"])
    rec.update({"status": "simulated", "metrics": metrics, "max_pos_err": max_err,
                "criteria": crit, "pass": all(crit.values()), "gains": tuning})
    return rec


def list_commands(commands_dir):
    files = sorted(f for f in os.listdir(commands_dir) if f.endswith(".txt"))
    out = []
    for fn in files:
        with open(os.path.join(commands_dir, fn)) as f:
            out.append((os.path.splitext(fn)[0], f.read()))
    return out
