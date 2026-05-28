#!/usr/bin/env python3
"""End-to-end driver for one command file.

Pipeline:
    parse_command -> plan_trajectory -> initial sim with baseline gains
    -> tune_gains -> final sim with best gains -> metrics + outputs.

This is a template — the agent should adapt:
  - load_system_params() to whatever schema system_params.yaml uses
  - initial state per mode (takeoff starts on ground; hover/land start in air)

Usage:
    python run_one.py \
        --command commands/001.txt \
        --params system_params.yaml \
        --out /root/results/001 \
        --dt 0.005
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cascade_pid import CascadePID, PIDGains      # noqa: E402
from metrics import compute_metrics                # noqa: E402
from parse_command import parse_command            # noqa: E402
from plot_results import write_plots               # noqa: E402
from quadrotor_dynamics import QuadParams, Quadrotor  # noqa: E402
from trajectory_planner import plan_trajectory     # noqa: E402
from tune_gains import gains_to_dict, success, tune  # noqa: E402


def load_system_params(path: Path) -> tuple[QuadParams, dict]:
    """Map system_params.yaml -> (QuadParams, dict of accel limits + dt)."""
    raw = yaml.safe_load(path.read_text())
    # Allow either flat or nested layouts.
    def g(k, default=None):
        if k in raw:
            return raw[k]
        for v in raw.values():
            if isinstance(v, dict) and k in v:
                return v[k]
        return default
    qp = QuadParams(
        mass=float(g("mass", 1.0)),
        Ixx=float(g("Ixx", 0.01)),
        Iyy=float(g("Iyy", 0.01)),
        Izz=float(g("Izz", 0.02)),
        arm_length=float(g("arm_length", 0.17)),
        kappa=float(g("kappa", 0.016)),
        max_thrust_per_motor=float(g("max_thrust_per_motor", 8.0)),
        tau_motor=float(g("tau_motor", 0.02)),
        g=float(g("g", 9.81)),
        motor_dirs=list(g("motor_dirs", [1, 1, -1, -1])),
    )
    limits = {
        "accel_limit_up": float(g("accel_limit_up", 5.0)),
        "accel_limit_down": float(g("accel_limit_down", 5.0)),
        "accel_limit_horiz": float(g("accel_limit_horiz", 5.0)),
        "dt": float(g("dt", 0.005)),
    }
    return qp, limits


def baseline_gains(mode: str) -> PIDGains:
    if mode in ("takeoff", "land", "hover"):
        return PIDGains(
            kp_pos=np.array([4.0, 4.0, 8.0]),
            ki_pos=np.array([0.0, 0.0, 0.5]),
            kd_pos=np.array([3.0, 3.0, 5.0]),
            kp_att=np.array([200.0, 200.0, 80.0]),
            ki_att=np.array([0.0, 0.0, 0.0]),
            kd_att=np.array([20.0, 20.0, 10.0]),
        )
    # fly
    return PIDGains(
        kp_pos=np.array([6.0, 6.0, 8.0]),
        ki_pos=np.array([0.0, 0.0, 0.0]),
        kd_pos=np.array([4.0, 4.0, 5.0]),
        kp_att=np.array([250.0, 250.0, 80.0]),
        ki_att=np.array([0.0, 0.0, 0.0]),
        kd_att=np.array([22.0, 22.0, 10.0]),
    )


def run(command_text: str, qp: QuadParams, limits: dict, dt: float,
        gains: PIDGains) -> tuple[np.ndarray, np.ndarray, dict, dict]:
    """Plan + simulate. Returns (planned, actual, sim_metrics, plan_meta)."""
    cmd = parse_command(command_text)
    plan = plan_trajectory(
        cmd["mode"], cmd["start"], cmd["end"], cmd["T"], dt,
        limits["accel_limit_up"], limits["accel_limit_down"],
        limits["accel_limit_horiz"],
    )
    planned = plan.desired
    N = planned.shape[1]

    sim = Quadrotor(qp)
    # Initial state: drone at planned[0:3, 0], zero velocity/attitude/rate.
    init_state = np.zeros(12)
    init_state[0:3] = planned[0:3, 0]
    sim.reset(init_state)
    ctrl = CascadePID(
        gains, qp.mass, qp.g, qp.arm_length, qp.kappa,
        qp.max_thrust_per_motor,
    )

    actual = np.zeros((15, N))
    for k in range(N):
        actual[0:3, k] = sim.state[0:3]
        actual[3:6, k] = sim.state[3:6]
        actual[6:9, k] = sim.state[6:9]
        actual[9:12, k] = sim.state[9:12]
        actual[12:15, k] = sim.world_accel()
        if k < N - 1:
            motors, _ = ctrl.step(planned[:, k], sim.state, dt)
            sim.step(motors, dt)

    err = np.linalg.norm(actual[0:3, :] - planned[0:3, :], axis=0)
    max_pos_err = float(np.max(err))
    m = compute_metrics(planned, actual, dt, cmd["mode"])
    sim_metrics = {
        "sse": m["SteadyStateError"],
        "overshoot_pct": m["Overshoot_pct"],
        "max_pos_err": max_pos_err,
        "metrics_3d": m,
    }
    plan_meta = {
        "mode": cmd["mode"], "T_requested": plan.T_requested,
        "T_used": plan.T_used, "extended": plan.extended,
        "max_accel_axis": plan.max_accel_axis,
    }
    return planned, actual, sim_metrics, plan_meta


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--command", required=True)
    p.add_argument("--params", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--dt", type=float, default=None)
    p.add_argument("--no-tune", action="store_true")
    args = p.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd_text = Path(args.command).read_text()
    qp, limits = load_system_params(Path(args.params))
    dt = args.dt if args.dt is not None else limits["dt"]
    cmd = parse_command(cmd_text)
    g0 = baseline_gains(cmd["mode"])

    def simulate_fn(g: PIDGains) -> dict:
        _, _, sm, _ = run(cmd_text, qp, limits, dt, g)
        return sm

    if args.no_tune:
        g_best = g0
        sm = simulate_fn(g0)
    else:
        g_best, sm = tune(simulate_fn, g0, cmd["mode"], verbose=True)

    planned, actual, _, plan_meta = run(cmd_text, qp, limits, dt, g_best)
    np.save(out_dir / "planned_trajectory.npy", planned)
    np.save(out_dir / "actual_trajectory.npy", actual)
    (out_dir / "metrics_3d.json").write_text(json.dumps(sm["metrics_3d"], indent=2))
    (out_dir / "tuning_results.json").write_text(json.dumps(gains_to_dict(g_best), indent=2))
    write_plots(planned, actual, dt, out_dir)
    print(json.dumps({
        "command": cmd_text,
        "plan_meta": plan_meta,
        "metrics": sm["metrics_3d"],
        "max_pos_err": sm["max_pos_err"],
        "success": success(sm),
        "out": str(out_dir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
