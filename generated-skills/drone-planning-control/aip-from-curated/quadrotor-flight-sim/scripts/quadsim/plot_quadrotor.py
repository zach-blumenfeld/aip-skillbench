"""Three 5x3 figures: desired vs actual, instantaneous error, cumulative |error|."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from quad_params import DEFAULT_PARAMS_PATH, _load_yaml

GROUPS = [
    ("Position", ["x", "y", "z"], "m"),
    ("Velocity", ["vx", "vy", "vz"], "m/s"),
    ("Orientation", [r"$\phi$", r"$\theta$", r"$\psi$"], "rad"),
    ("Angular velocity", ["p", "q", "r"], "rad/s"),
    ("Acceleration", ["ax", "ay", "az"], "m/s²"),
]


def plot_quadrotor(state, state_des, time_vec, save_dir, params_path=None):
    """state, state_des: (15 x n); time_vec: (n,). Writes 3 PNGs into save_dir."""
    sample_rate = float(_load_yaml(params_path or DEFAULT_PARAMS_PATH)["sample_rate"])
    time_step = 1.0 / sample_rate
    state, state_des = np.asarray(state), np.asarray(state_des)
    error = state - state_des
    cumulative = time_step * np.cumsum(np.abs(error), axis=1)
    os.makedirs(save_dir, exist_ok=True)
    figures = {
        "desired_vs_actual.png": "Desired (blue) vs actual (red)",
        "errors.png": "Instantaneous error (actual - desired)",
        "cumulative_errors.png": "Cumulative absolute error (time_step * cumsum|error|)",
    }
    paths = []
    for fname, title in figures.items():
        fig, axes = plt.subplots(5, 3, figsize=(16, 20))
        fig.suptitle(title)
        for g, (gname, labels, unit) in enumerate(GROUPS):
            for j in range(3):
                r = 3 * g + j
                ax = axes[g, j]
                if fname == "desired_vs_actual.png":
                    ax.plot(time_vec, state_des[r], "b-", label="desired")
                    ax.plot(time_vec, state[r], "r-", label="actual")
                    if g == 0 and j == 0:
                        ax.legend()
                    ax.set_ylabel(f"{labels[j]} [{unit}]")
                elif fname == "errors.png":
                    ax.plot(time_vec, error[r], "k-")
                    ax.set_ylabel(f"{labels[j]} error [{unit}]")
                else:
                    ax.plot(time_vec, cumulative[r], "m-")
                    ax.set_ylabel(f"{labels[j]} cum. |err| [{unit}·s]")
                ax.set_title(f"{gname}: {labels[j]}")
                ax.set_xlabel("time [s]")
                ax.grid(True)
        fig.tight_layout(rect=(0, 0, 1, 0.98))
        path = os.path.join(save_dir, fname)
        fig.savefig(path)
        plt.close(fig)
        paths.append(path)
    return paths
