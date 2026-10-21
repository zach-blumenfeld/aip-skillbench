"""Desired-vs-actual, error, and cumulative-error figures for a (15 x n) run.

Requires: Python >= 3.8, numpy, matplotlib, pyyaml.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

GROUPS = [
    ("Position [m]", slice(0, 3), ["x", "y", "z"]),
    ("Velocity [m/s]", slice(3, 6), [r"$v_x$", r"$v_y$", r"$v_z$"]),
    ("Orientation [rad]", slice(6, 9), [r"$\phi$", r"$\theta$", r"$\psi$"]),
    ("Angular velocity [rad/s]", slice(9, 12), ["p", "q", "r"]),
    ("Acceleration [m/s^2]", slice(12, 15), [r"$a_x$", r"$a_y$", r"$a_z$"]),
]


def plot_quadrotor(state, state_des, time_vec, save_dir, params_path="/root/system_params.yaml"):
    """Save desired_vs_actual.png, errors.png, cumulative_errors.png into save_dir."""
    with open(params_path) as f:
        time_step = 1.0 / float(yaml.safe_load(f)["sample_rate"])
    os.makedirs(save_dir, exist_ok=True)
    figs = {name: plt.subplots(5, 3, figsize=(16, 20)) for name in ("desired_vs_actual", "errors", "cumulative_errors")}
    for r, (title, sl, labels) in enumerate(GROUPS):
        act, des = state[sl], state_des[sl]
        err = act - des
        cum = time_step * np.cumsum(np.abs(err), axis=1)
        for c in range(3):
            ax = figs["desired_vs_actual"][1][r, c]
            ax.plot(time_vec, des[c], "b-", label="desired")
            ax.plot(time_vec, act[c], "r--", label="actual")
            figs["errors"][1][r, c].plot(time_vec, err[c], "k-")
            figs["cumulative_errors"][1][r, c].plot(time_vec, cum[c], "m-")
            for name in figs:
                a = figs[name][1][r, c]
                a.set_title(f"{title}: {labels[c]}")
                a.set_xlabel("t [s]")
                a.grid(True)
            if r == 0 and c == 0:
                ax.legend()
    for name, (fig, _) in figs.items():
        fig.suptitle({"desired_vs_actual": "Desired (blue) vs actual (red)",
                      "errors": "Error = actual - desired",
                      "cumulative_errors": "Cumulative |error| x time_step"}[name])
        fig.tight_layout(rect=[0, 0, 1, 0.98])
        fig.savefig(os.path.join(save_dir, f"{name}.png"), dpi=80)
        plt.close(fig)
