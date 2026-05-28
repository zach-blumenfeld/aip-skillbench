"""Generate the three required plot PNGs under <results_dir>/plots/.

  - desired_vs_actual.png : three stacked subplots, position desired vs actual
                            for x, y, z.
  - errors.png            : per-axis signed error + Euclidean error vs the
                            0.05 m spec line.
  - cumulative_errors.png : time-integrated |error| per axis and Euclidean.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def generate(planned: dict, actual: dict, results_dir: str) -> list[str]:
    M = planned["matrix"]
    A = actual["matrix"]
    dt = planned["dt"]
    t = np.arange(M.shape[1]) * dt
    plots_dir = os.path.join(results_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)

    # 1) desired vs actual position
    fig, axs = plt.subplots(3, 1, figsize=(8, 8), sharex=True)
    for i, lbl in enumerate(["x", "y", "z"]):
        axs[i].plot(t, M[i], "--", label=f"{lbl}_desired")
        axs[i].plot(t, A[i], label=f"{lbl}_actual")
        axs[i].set_ylabel(f"{lbl} (m)")
        axs[i].grid(True)
        axs[i].legend(loc="best")
    axs[-1].set_xlabel("t (s)")
    fig.suptitle("Desired vs Actual Position")
    fig.tight_layout()
    p1 = os.path.join(plots_dir, "desired_vs_actual.png")
    fig.savefig(p1, dpi=120)
    plt.close(fig)

    # 2) errors
    err = M[0:3] - A[0:3]
    eu = np.linalg.norm(err, axis=0)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, lbl in enumerate(["x", "y", "z"]):
        ax.plot(t, err[i], label=f"e_{lbl}")
    ax.plot(t, eu, "k-", linewidth=1.5, label="Euclidean")
    ax.axhline(0.05, color="r", linestyle=":", label="spec 0.05 m")
    ax.axhline(-0.05, color="r", linestyle=":")
    ax.set_xlabel("t (s)")
    ax.set_ylabel("error (m)")
    ax.set_title("Position Tracking Error")
    ax.grid(True)
    ax.legend(loc="best")
    fig.tight_layout()
    p2 = os.path.join(plots_dir, "errors.png")
    fig.savefig(p2, dpi=120)
    plt.close(fig)

    # 3) cumulative
    cum = np.cumsum(np.abs(err) * dt, axis=1)
    cum_e = np.cumsum(eu * dt)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, lbl in enumerate(["x", "y", "z"]):
        ax.plot(t, cum[i], label=f"int_|e_{lbl}|")
    ax.plot(t, cum_e, "k-", linewidth=1.5, label="int_Euclidean")
    ax.set_xlabel("t (s)")
    ax.set_ylabel("cumulative |error| (m·s)")
    ax.set_title("Cumulative Position Error")
    ax.grid(True)
    ax.legend(loc="best")
    fig.tight_layout()
    p3 = os.path.join(plots_dir, "cumulative_errors.png")
    fig.savefig(p3, dpi=120)
    plt.close(fig)

    return [p1, p2, p3]
