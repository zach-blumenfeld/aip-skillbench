"""Quadrotor simulation plotter — three figures per run.

Given the actual and desired state matrices from a quadrotor simulation
run, produces three matplotlib figures (5x3 subplot grids) covering all
five state groups and writes them as PNG files to a caller-supplied
directory. No path is hardcoded inside the figure-saving logic.

State matrix layout (15 rows x n samples)
-----------------------------------------
rows  0:3   position     [x, y, z]
rows  3:6   velocity     [vx, vy, vz]
rows  6:9   orientation  [phi, theta, psi]
rows  9:12  angular vel  [p, q, r]
rows 12:15  acceleration [ax, ay, az]

NOTE: the curated SKILL.md groups them in the order
position -> orientation -> velocity -> angular velocity -> acceleration
for plotting, which matches the original quadrotor plotter convention.

Outputs (PNG, dpi=100, figsize=(16, 20))
----------------------------------------
{save_dir}/desired_vs_actual.png   — Figure 1: blue (desired) vs red (actual)
{save_dir}/errors.png              — Figure 2: instantaneous error = actual - desired
{save_dir}/cumulative_errors.png   — Figure 3: time_step * cumsum(|error|)

`time_step` is **not** hardcoded. By default it is derived from
`sample_rate` in `/root/system_params.yaml` (`time_step = 1 /
sample_rate`). Callers running outside the standard environment may
override the path via `system_params_path=` or pass `time_step=`
directly.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")  # noqa: E402  — headless backend before pyplot
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402


DEFAULT_SYSTEM_PARAMS = "/root/system_params.yaml"


# ----- params --------------------------------------------------------------


def load_time_step(system_params_path: str = DEFAULT_SYSTEM_PARAMS) -> float:
    """Derive `time_step` from the simulator's sample rate.

    Reads `sample_rate` (Hz) from the system-parameters YAML and returns
    `1 / sample_rate`. Kept as its own helper so the dependence on
    `system_params.yaml` is explicit — the curated SKILL.md is emphatic
    that `time_step` must never be hardcoded.
    """
    with open(system_params_path) as f:
        params = yaml.safe_load(f)
    return 1.0 / float(params["sample_rate"])


# ----- groups --------------------------------------------------------------


def slice_state_groups(state: np.ndarray, state_des: np.ndarray):
    """Split the (15, n) state matrices into the five plotting groups.

    Returns a list of (desired, actual, ylabels, overlay_titles,
    error_titles, cum_titles) tuples — one tuple per row of the 5x3
    subplot grid. Order matches the curated SKILL.md's
    Position / Orientation / Velocity / Angular velocity / Acceleration
    convention.
    """
    pos = state[0:3]
    vel = state[3:6]
    rpy = state[6:9]
    av = state[9:12]
    acc = state[12:15]

    pd = state_des[0:3]
    vd = state_des[3:6]
    rd = state_des[6:9]
    avd = state_des[9:12]
    acd = state_des[12:15]

    return [
        (
            pd,
            pos,
            ["x [m]", "y [m]", "z [m]"],
            ["Position in x", "Position in y", "Position in z"],
            ["Error in x", "Error in y", "Error in z"],
            [
                "Accumulative Error in x",
                "Accumulative Error in y",
                "Accumulative Error in z",
            ],
        ),
        (
            rd,
            rpy,
            [r"$\phi$", r"$\theta$", r"$\psi$"],
            [
                r"Orientation in $\phi$",
                r"Orientation in $\theta$",
                r"Orientation in $\psi$",
            ],
            [r"Error in $\phi$", r"Error in $\theta$", r"Error in $\psi$"],
            [
                r"Accumulative Error in $\phi$",
                r"Accumulative Error in $\theta$",
                r"Accumulative Error in $\psi$",
            ],
        ),
        (
            vd,
            vel,
            ["vx [m/s]", "vy [m/s]", "vz [m/s]"],
            ["Velocity in x", "Velocity in y", "Velocity in z"],
            [r"Error in $v_x$", r"Error in $v_y$", r"Error in $v_z$"],
            [
                r"Accumulative Error in $v_x$",
                r"Accumulative Error in $v_y$",
                r"Accumulative Error in $v_z$",
            ],
        ),
        (
            avd,
            av,
            [r"$\omega_x$", r"$\omega_y$", r"$\omega_z$"],
            [
                r"Angular Velocity $\omega_x$",
                r"Angular Velocity $\omega_y$",
                r"Angular Velocity $\omega_z$",
            ],
            [
                r"Error in $\omega_x$",
                r"Error in $\omega_y$",
                r"Error in $\omega_z$",
            ],
            [
                r"Accumulative Error in $\omega_x$",
                r"Accumulative Error in $\omega_y$",
                r"Accumulative Error in $\omega_z$",
            ],
        ),
        (
            acd,
            acc,
            [r"ax [m/s$^2$]", r"ay [m/s$^2$]", r"az [m/s$^2$]"],
            [
                r"Acceleration $a_x$",
                r"Acceleration $a_y$",
                r"Acceleration $a_z$",
            ],
            [r"Error in $a_x$", r"Error in $a_y$", r"Error in $a_z$"],
            [
                r"Accumulative Error in $a_x$",
                r"Accumulative Error in $a_y$",
                r"Accumulative Error in $a_z$",
            ],
        ),
    ]


# ----- figure rendering ----------------------------------------------------


def _new_grid():
    """5x3 figure sized to prevent label overlap."""
    return plt.figure(figsize=(16, 20))


def _render_overlay(fig, groups, time_vec):
    """Figure 1 — blue desired vs red actual overlay."""
    for row, (des, act, ylabels, titles, _err_titles, _cum_titles) in enumerate(groups):
        for col in range(3):
            ax = fig.add_subplot(5, 3, row * 3 + col + 1)
            ax.plot(time_vec, des[col], "b", label="Desired")
            ax.plot(time_vec, act[col], "r", label="Actual")
            ax.legend()
            ax.grid(True)
            ax.set_xlabel("time [s]")
            ax.set_ylabel(ylabels[col])
            ax.set_title(titles[col])


def _render_errors(fig, groups, time_vec):
    """Figure 2 — instantaneous error = actual - desired."""
    for row, (des, act, ylabels, _titles, err_titles, _cum_titles) in enumerate(groups):
        err = act - des
        for col in range(3):
            ax = fig.add_subplot(5, 3, row * 3 + col + 1)
            ax.plot(time_vec, err[col], "r")
            ax.grid(True)
            ax.set_xlabel("time [s]")
            ax.set_ylabel(ylabels[col])
            ax.set_title(err_titles[col])


def _render_cumulative(fig, groups, time_vec, time_step):
    """Figure 3 — integrated absolute error: time_step * cumsum(|error|)."""
    for row, (des, act, ylabels, _titles, _err_titles, cum_titles) in enumerate(groups):
        err = act - des
        for col in range(3):
            ax = fig.add_subplot(5, 3, row * 3 + col + 1)
            ax.plot(time_vec, time_step * np.cumsum(np.abs(err[col])), "r")
            ax.grid(True)
            ax.set_xlabel("time [s]")
            ax.set_ylabel(ylabels[col])
            ax.set_title(cum_titles[col])


# ----- entrypoint ----------------------------------------------------------


def plot_quadrotor(
    state,
    state_des,
    time_vec,
    save_dir,
    *,
    time_step: float | None = None,
    system_params_path: str = DEFAULT_SYSTEM_PARAMS,
):
    """Produce the three quadrotor result figures and write them to disk.

    Parameters
    ----------
    state, state_des : np.ndarray, shape (15, n)
        Actual and desired state matrices (see module docstring for the
        row layout).
    time_vec : np.ndarray, shape (n,)
        Time axis in seconds.
    save_dir : str
        Directory the three PNG files are written to. Created via
        `os.makedirs(save_dir, exist_ok=True)`. Caller-supplied —
        nothing here is hardcoded.
    time_step : float, optional
        Sample interval (seconds) used for the cumulative-error
        integral. When omitted, derived from `system_params.yaml`.
    system_params_path : str, optional
        Override for the system parameters file. Defaults to
        `/root/system_params.yaml`.
    """
    state = np.asarray(state)
    state_des = np.asarray(state_des)
    time_vec = np.asarray(time_vec)

    if state.shape[0] != 15 or state_des.shape[0] != 15:
        raise ValueError(
            f"state and state_des must each have 15 rows; got "
            f"{state.shape} and {state_des.shape}"
        )

    if time_step is None:
        time_step = load_time_step(system_params_path)

    groups = slice_state_groups(state, state_des)
    os.makedirs(save_dir, exist_ok=True)

    renderers = [
        ("desired_vs_actual", _render_overlay, ()),
        ("errors", _render_errors, ()),
        ("cumulative_errors", _render_cumulative, (time_step,)),
    ]
    for name, render, extra in renderers:
        fig = _new_grid()
        render(fig, groups, time_vec, *extra)
        fig.tight_layout()
        fig.savefig(os.path.join(save_dir, name + ".png"), dpi=100)
        plt.close(fig)

    print(f"Saved plots to '{save_dir}'")
