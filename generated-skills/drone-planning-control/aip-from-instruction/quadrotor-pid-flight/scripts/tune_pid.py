"""PID gain search.

Strategy:
  1. Evaluate hand-tuned defaults for a 1 kg near-hover quadrotor.
  2. Scale-grid search over (kp_pos, kd_pos, kp_att+kd_att) joint scalars.
  3. Optional second pass widens kp_pos range if specs still fail.

Score (lower is better):
    max(|euclidean position error|) + 0.01 * Overshoot_pct + SteadyStateError

Returns the best gains seen and the corresponding simulated actual trajectory.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_metrics import compute_metrics  # noqa: E402
from simulate import simulate  # noqa: E402


DEFAULT_GAINS = dict(
    kp_pos=[8.0, 8.0, 10.0],
    ki_pos=[0.4, 0.4, 1.0],
    kd_pos=[5.0, 5.0, 6.0],
    kp_att=[60.0, 60.0, 16.0],
    ki_att=[0.0, 0.0, 0.0],
    kd_att=[8.0, 8.0, 4.0],
)

POS_ERR_SPEC = 0.05
OVERSHOOT_SPEC = 5.0
SSE_SPEC = 0.05


def _scaled(base: list[float], k: float) -> list[float]:
    return [float(b * k) for b in base]


def _score(planned: dict, actual: dict, command: dict) -> tuple[float, dict, list[str]]:
    M = planned["matrix"]
    A = actual["matrix"]
    err_xyz = M[0:3] - A[0:3]
    eu = np.linalg.norm(err_xyz, axis=0)
    metrics = compute_metrics(planned, actual, command)
    fails = []
    if eu.max() >= POS_ERR_SPEC:
        fails.append(f"pos_err_max={eu.max():.4f}")
    if metrics["Overshoot_pct"] >= OVERSHOOT_SPEC:
        fails.append(f"overshoot={metrics['Overshoot_pct']:.2f}")
    if metrics["SteadyStateError"] >= SSE_SPEC:
        fails.append(f"sse={metrics['SteadyStateError']:.4f}")
    score = float(eu.max()) + 0.01 * metrics["Overshoot_pct"] + metrics["SteadyStateError"]
    return score, metrics, fails


def _try(planned, params, command, gains):
    actual = simulate(planned, params, gains)
    score, metrics, fails = _score(planned, actual, command)
    return {"gains": gains, "actual": actual, "metrics": metrics,
            "score": score, "fails": fails}


def tune(planned: dict, params: dict, command: dict,
         max_evals: int = 60) -> dict:
    base = {k: list(v) for k, v in DEFAULT_GAINS.items()}
    best = _try(planned, params, command, base)
    evals = 1
    if not best["fails"]:
        return {**best, "iterations": evals, "passed": True}

    # scale grid (kp_pos_scale, kd_pos_scale, att_scale)
    pos_p_scales = [1.0, 0.7, 1.3, 0.5, 1.6, 0.85, 1.15]
    pos_d_scales = [1.0, 0.7, 1.3, 0.85, 1.15]
    att_scales = [1.0, 0.7, 1.3, 0.85, 1.15]

    for sp in pos_p_scales:
        for sd in pos_d_scales:
            for sa in att_scales:
                if evals >= max_evals:
                    break
                gains = {
                    "kp_pos": _scaled(base["kp_pos"], sp),
                    "ki_pos": base["ki_pos"],
                    "kd_pos": _scaled(base["kd_pos"], sd),
                    "kp_att": _scaled(base["kp_att"], sa),
                    "ki_att": base["ki_att"],
                    "kd_att": _scaled(base["kd_att"], sa),
                }
                cand = _try(planned, params, command, gains)
                evals += 1
                if cand["score"] < best["score"]:
                    best = cand
                if not cand["fails"]:
                    return {**cand, "iterations": evals, "passed": True}
            if evals >= max_evals:
                break
        if evals >= max_evals:
            break

    return {**best, "iterations": evals, "passed": not best["fails"]}
