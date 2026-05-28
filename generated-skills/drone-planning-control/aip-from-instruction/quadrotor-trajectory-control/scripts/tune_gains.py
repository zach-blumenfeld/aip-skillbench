#!/usr/bin/env python3
"""Coarse-to-fine local search over cascade PID gains for one command.

Cost function — designed so success criteria dominate:
    cost = 100 * max(0, max_pos_err   - 0.05)        # per-timestep error
         + 100 * max(0, sse           - 0.05)        # steady-state error
         +  10 * max(0, overshoot_pct - 5.0)         # overshoot
         +   1 * max_pos_err                         # tie-break (track tighter)

Search loop:
  1. Start at baseline gains (passed in).
  2. Round 0 (coarse): multiplicative factors {0.5, 1.0, 2.0} on kp_pos[2],
     kd_pos[2], kp_att (yaw-and-roll/pitch shared), kd_att shared.
     Pick the best combo (or stay at baseline).
  3. Round 1 (fine): factors {0.75, 1.0, 1.5} on the same knobs.
  4. Round 2 (xy): same factors on kp_pos[0:2], kd_pos[0:2].
  5. Stop early if all success criteria pass.

`simulate_fn(gains) -> dict` must return:
    {"sse": float, "overshoot_pct": float, "max_pos_err": float}

This module is import-only by run_one.py; no CLI.
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import asdict

import numpy as np

from cascade_pid import PIDGains


def cost(metrics: dict) -> float:
    sse = metrics["sse"]
    osp = metrics["overshoot_pct"]
    mpe = metrics["max_pos_err"]
    return (
        100.0 * max(0.0, mpe - 0.05)
        + 100.0 * max(0.0, sse - 0.05)
        + 10.0 * max(0.0, osp - 5.0)
        + 1.0 * mpe
    )


def success(metrics: dict) -> bool:
    return (
        metrics["sse"] < 0.05
        and metrics["overshoot_pct"] < 5.0
        and metrics["max_pos_err"] < 0.05
    )


def _scaled(gains: PIDGains, knob: str, factor: float) -> PIDGains:
    g = PIDGains(
        kp_pos=gains.kp_pos.copy(),
        ki_pos=gains.ki_pos.copy(),
        kd_pos=gains.kd_pos.copy(),
        kp_att=gains.kp_att.copy(),
        ki_att=gains.ki_att.copy(),
        kd_att=gains.kd_att.copy(),
    )
    if knob == "kp_pos_z":
        g.kp_pos[2] *= factor
    elif knob == "kd_pos_z":
        g.kd_pos[2] *= factor
    elif knob == "kp_pos_xy":
        g.kp_pos[0] *= factor; g.kp_pos[1] *= factor
    elif knob == "kd_pos_xy":
        g.kd_pos[0] *= factor; g.kd_pos[1] *= factor
    elif knob == "kp_att":
        g.kp_att *= factor
    elif knob == "kd_att":
        g.kd_att *= factor
    return g


def tune(simulate_fn, baseline: PIDGains, mode: str,
         max_rounds: int = 3, verbose: bool = False):
    rounds = [
        (["kp_pos_z", "kd_pos_z", "kp_att", "kd_att"], [0.5, 1.0, 2.0]),
        (["kp_pos_z", "kd_pos_z", "kp_att", "kd_att"], [0.75, 1.0, 1.5]),
        (["kp_pos_xy", "kd_pos_xy"], [0.75, 1.0, 1.5]),
    ]
    best = baseline
    best_metrics = simulate_fn(best)
    best_cost = cost(best_metrics)
    if verbose:
        print(f"  baseline cost={best_cost:.4f} metrics={best_metrics}")
    if success(best_metrics):
        return best, best_metrics

    for r, (knobs, factors) in enumerate(rounds[:max_rounds]):
        improved = True
        while improved:
            improved = False
            for knob, f in itertools.product(knobs, factors):
                if f == 1.0:
                    continue
                trial = _scaled(best, knob, f)
                m = simulate_fn(trial)
                c = cost(m)
                if c < best_cost - 1e-6:
                    best, best_metrics, best_cost = trial, m, c
                    improved = True
                    if verbose:
                        print(f"  r{r} {knob}*{f} -> cost={c:.4f} {m}")
                    if success(m):
                        return best, best_metrics
    return best, best_metrics


def gains_to_dict(g: PIDGains) -> dict:
    return {
        "kp_pos": g.kp_pos.tolist(),
        "ki_pos": g.ki_pos.tolist(),
        "kd_pos": g.kd_pos.tolist(),
        "kp_att": g.kp_att.tolist(),
        "ki_att": g.ki_att.tolist(),
        "kd_att": g.kd_att.tolist(),
    }
