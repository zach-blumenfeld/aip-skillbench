#!/usr/bin/env python3
"""Emit the three required plots into <out_dir>/plots/.

  - desired_vs_actual.png : 3 subplots (x, y, z) of planned vs actual position.
  - errors.png            : per-axis error and Euclidean error vs time.
  - cumulative_errors.png : integrated |error| vs time.

Usage:
    from plot_results import write_plots
    write_plots(planned, actual, dt, out_dir)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def write_plots(planned: np.ndarray, actual: np.ndarray, dt: float,
                out_dir: Path | str) -> None:
    out_dir = Path(out_dir)
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    N = planned.shape[1]
    t = np.arange(N) * dt

    # 1. desired vs actual
    fig, axes = plt.subplots(3, 1, figsize=(8, 8), sharex=True)
    for i, lbl in enumerate(["x", "y", "z"]):
        axes[i].plot(t, planned[i, :], label="planned", linewidth=2)
        axes[i].plot(t, actual[i, :N], label="actual", linewidth=1.2,
                     linestyle="--")
        axes[i].set_ylabel(f"{lbl} (m)")
        axes[i].grid(True, alpha=0.3)
        axes[i].legend(loc="best")
    axes[-1].set_xlabel("time (s)")
    fig.suptitle("Desired vs Actual Position")
    fig.tight_layout()
    fig.savefig(plots_dir / "desired_vs_actual.png", dpi=120)
    plt.close(fig)

    # 2. per-axis + euclidean error
    err = actual[0:3, :N] - planned[0:3, :]
    eucl = np.linalg.norm(err, axis=0)
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, lbl in enumerate(["ex", "ey", "ez"]):
        ax.plot(t, err[i, :], label=lbl)
    ax.plot(t, eucl, label="‖e‖", linewidth=2, color="black")
    ax.axhline(0.05, linestyle=":", color="red", label="0.05 m limit")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("error (m)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(plots_dir / "errors.png", dpi=120)
    plt.close(fig)

    # 3. cumulative |error|
    cum = np.cumsum(np.abs(err), axis=1) * dt
    cum_e = np.cumsum(eucl) * dt
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, lbl in enumerate(["x", "y", "z"]):
        ax.plot(t, cum[i, :], label=f"∫|e_{lbl}|")
    ax.plot(t, cum_e, label="∫‖e‖", linewidth=2, color="black")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("cumulative error (m·s)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(plots_dir / "cumulative_errors.png", dpi=120)
    plt.close(fig)
