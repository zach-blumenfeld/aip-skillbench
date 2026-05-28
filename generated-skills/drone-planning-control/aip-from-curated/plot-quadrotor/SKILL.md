---
name: plot-quadrotor
description: Use this skill when visualising drone simulation results. Produces three matplotlib figures — desired vs actual trajectories, instantaneous error, and cumulative absolute error — for all 5 state groups (position, orientation, velocity, angular velocity, acceleration). Saves figures to a plots/ directory automatically.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3, numpy, pyyaml, and matplotlib (Agg backend — used without a display). Reads sample_rate from /root/system_params.yaml.
---

```yaml
purpose: >
  Render the standard quadrotor-simulation result figures from a (15,
  n) actual-state matrix and a (15, n) desired-state matrix. Produces
  exactly three PNGs — `desired_vs_actual.png`, `errors.png`,
  `cumulative_errors.png` — each a 5x3 grid covering the five state
  groups (position, orientation, velocity, angular velocity,
  acceleration) across their three axes. The save directory is
  supplied by the caller and created on demand; the time step used for
  the cumulative-error integral is derived from `sample_rate` in
  `/root/system_params.yaml` so a runtime parameter change cannot
  silently desynchronize the plots from the simulator.

trigger_when:
  - A simulation run has produced `actual_trajectory.npy` and `planned_trajectory.npy` and the caller needs the standard three diagnostic figures.
  - Inside the simulator main loop after the per-command state matrices are assembled, before metrics are written.
  - Debugging tracking error — overlay (Fig 1), instantaneous error (Fig 2), and integrated absolute error (Fig 3) are needed side by side.
  - Re-rendering plots for a previously saved run by reloading the two `.npy` matrices and a recomputed time vector.

do_not_use_when:
  - Computing scalar tracking metrics like RiseTime, SettlingTime, Overshoot, or SteadyStateError (use `stepinfo-3d`).
  - Generating the planned trajectory itself (use `position-controller-trajectory-planner`).
  - Plotting non-quadrotor data or any state matrix whose row layout differs from the 15-row convention below.

scope_and_approval: >
  Pure rendering. Writes three PNG files under `save_dir` (creating the
  directory if needed) and prints one confirmation line. Reads
  `/root/system_params.yaml` for `sample_rate`. No other filesystem,
  network, or user-visible side effects. Safe to run without
  prompting.

steps:
  - name: load-time-step
    description: >
      Read `sample_rate` (Hz) from `/root/system_params.yaml` and
      return `time_step = 1 / sample_rate`. The curated source is
      emphatic that `time_step` must NEVER be hardcoded — a sample-rate
      change in the YAML must flow through to the cumulative-error
      integral without any code edit.
    script: scripts/plot_quadrotor.py
    outputs:
      - name: time_step
        type: float
        description: Seconds per simulation sample; used as the dx of the cumulative-error integral.

  - name: slice-state-groups
    description: >
      Split the (15, n) `state` and `state_des` matrices into the five
      plotting groups — position (rows 0:3), orientation (rows 6:9),
      velocity (rows 3:6), angular velocity (rows 9:12), and
      acceleration (rows 12:15). Group order in the figure rows
      follows the curated convention
      Position -> Orientation -> Velocity -> Angular velocity ->
      Acceleration; it is intentionally not the row order of the state
      matrix. Each group carries its three y-axis labels and the
      titles for the three figure types.
    script: scripts/plot_quadrotor.py
    inputs:
      - name: state
        type: object
        description: Actual state matrix, shape (15, n).
      - name: state_des
        type: object
        description: Desired state matrix, shape (15, n).
    outputs:
      - name: groups
        type: list[object]
        description: Five (des, act, ylabels, overlay_titles, error_titles, cum_titles) tuples — one per figure row.

  - name: render-figures
    description: >
      Build the three figures, each as a 5x3 subplot grid at
      `figsize=(16, 20)` (sized to prevent label overlap). For every
      row x column the script grids the data and labels the axes with
      the group's `ylabels` and per-figure title set. Figure-specific
      rendering — overlay vs error vs cumulative-error — is selected
      from the `figure` input. Instantaneous error is `actual - desired`
      drawn in red. Cumulative absolute error is
      `time_step * np.cumsum(np.abs(error))` so its units are
      `[unit * seconds]`, matching the curated spec.
    script: scripts/plot_quadrotor.py
    depends_on: [load-time-step, slice-state-groups]
    inputs:
      - name: figure
        type: string
        description: One of `desired_vs_actual`, `errors`, `cumulative_errors`.
      - name: groups
        type: list[object]
      - name: time_vec
        type: object
        description: Time axis (seconds), shape (n,).
      - name: time_step
        type: float
    outputs:
      - name: figure_object
        type: object
        description: A populated matplotlib Figure, ready to save.

  - name: save-and-close
    description: >
      Create `save_dir` if missing (`os.makedirs(save_dir,
      exist_ok=True)`), write each figure as `{figure}.png` at
      `dpi=100`, and close it with `plt.close(fig)` to release memory.
      `save_dir` is taken verbatim from the caller — the script must
      NOT hardcode `/root/results/...` or any other absolute path. The
      three files written are `desired_vs_actual.png`, `errors.png`,
      `cumulative_errors.png`.
    script: scripts/plot_quadrotor.py
    depends_on: [render-figures]
    inputs:
      - name: figure_object
        type: object
      - name: save_dir
        type: string
      - name: figure_name
        type: string
    outputs:
      - name: png_path
        type: string
        description: Path of the saved PNG file.

modes:
  - name: per-command
    body: >
      Inside the simulator main loop, call `plot_quadrotor(actual,
      desired, time_vec, save_dir=os.path.join(out_dir, 'plots'))`
      once per command after the per-command state matrices are
      assembled and before `metrics_3d.json` is written. `save_dir`
      should be the command's `plots/` subdirectory under
      `/root/results/<label>/`.
  - name: post-hoc-replot
    body: >
      Reload `actual_trajectory.npy` and `planned_trajectory.npy` for a
      previously saved command, rebuild `time_vec` via
      `np.arange(0, T, time_step)` (with `time_step` from
      `system_params.yaml`), and call `plot_quadrotor(...)` again.
      Idempotent — overwrites the prior PNGs.

scenarios:
  - need: Render the three standard figures for command `001` after a simulation pass.
    context: The main loop has produced `actual` and `desired` (15, n) matrices and a `time_vec` of length n. `out_dir = '/root/results/001'`.
    action: "`plot_quadrotor(actual, desired, time_vec, save_dir=os.path.join(out_dir, 'plots'))` — the script reads `sample_rate` from `system_params.yaml`, derives `time_step`, and writes three PNGs under `/root/results/001/plots/`."
    outcome: "`desired_vs_actual.png`, `errors.png`, and `cumulative_errors.png` exist under the command's `plots/` directory, each a 5x3 grid covering position, orientation, velocity, angular velocity, and acceleration."
  - need: Re-render plots after the simulator's `sample_rate` is bumped from 200 Hz to 500 Hz.
    context: Hardcoding `time_step = 0.005` in the plotter would now produce a cumulative-error integral that is wrong by a factor of 2.5.
    action: Leave the call site unchanged. Because `load-time-step` reads `sample_rate` from `system_params.yaml`, the new `time_step = 1/500` flows through automatically.
    outcome: Cumulative-error magnitudes match the new sample rate without a code edit.

integrations:
  - partner: position-controller-trajectory-planner / motor-model-dynamics
    body: >
      Consumes the actual-state trajectory those skills produce by
      integrating the simulator across the command horizon. Pairs
      directly with the (15, n) state matrices stored as
      `actual_trajectory.npy` / `planned_trajectory.npy` per the
      task's instruction.md schema.
  - partner: stepinfo-3d
    body: >
      Plots are the visual companion to the scalar step-response
      metrics `stepinfo-3d` writes to `metrics_3d.json`. Plots usually
      land in `plots/` before metrics are written so a failed metrics
      assertion still leaves the diagnostic figures behind.

anti_patterns:
  - Hardcoding `time_step` (e.g. `time_step = 0.005`). The curated source is explicit — always derive it from `sample_rate` in `system_params.yaml` so a sample-rate change cannot silently invalidate the cumulative-error figure.
  - Hardcoding the save path (e.g. `/root/results/001/plots`). `save_dir` is supplied by the caller and may differ per command or per environment. Use it verbatim and only ever `os.makedirs(save_dir, exist_ok=True)` on it.
  - Plotting the five groups in state-row order (position, velocity, orientation, angular velocity, acceleration). The curated row order is position, orientation, velocity, angular velocity, acceleration — swapping velocity and orientation makes the figures unreadable next to the canonical examples.
  - Forgetting `time_step *` in the cumulative-error integral. Plain `cumsum(|error|)` has units of `[unit * samples]`, not `[unit * seconds]`, and the magnitudes will scale wrongly with sample rate.
  - Skipping `plt.close(fig)`. Across a multi-command run the figure objects accumulate in memory and matplotlib eventually warns or crashes.
  - Using plain ASCII for the orientation labels (`phi`, `theta`, `psi`). The curated spec calls for the LaTeX strings `r'$\phi$'`, `r'$\theta$'`, `r'$\psi$'` so matplotlib renders them as proper Greek letters.
  - Shrinking the figure below `figsize=(16, 20)`. The 5x3 grid is dense; smaller figures overlap subplot titles and axis labels and the diagnostic value drops sharply.
  - Choosing a non-Agg matplotlib backend. The task environment is headless; default backends that require a display will crash. Importing matplotlib with `matplotlib.use('Agg')` before `pyplot` is mandatory.
```
