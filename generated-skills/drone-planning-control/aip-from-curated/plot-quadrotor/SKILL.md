---
name: plot-quadrotor
description: Use this skill when visualising drone simulation results. Produces three matplotlib figures — desired vs actual trajectories, instantaneous error, and cumulative absolute error — for all 5 state groups (position, orientation, velocity, angular velocity, acceleration). Saves figures to a plots/ directory automatically.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Visualise the results of a quadrotor simulation run. Given actual and desired
  state matrices over time, generate three matplotlib figures (desired vs
  actual overlay, instantaneous error, cumulative absolute error) for all 5
  state groups — position, velocity, orientation, angular velocity,
  acceleration — and save them as PNG files into a caller-supplied directory.

trigger_when:
  - Visualising drone or quadrotor simulation results.
  - A caller passes `state`, `state_des`, and `time_vec` and asks for plots.
  - Comparing desired vs actual trajectories or computing tracking-error plots
    from a simulation run.

scope_and_approval: >
  Input contract:
    state     : (15 x n) numpy array — actual drone state over time
    state_des : (15 x n) numpy array — desired drone state over time
    time_vec  : (n,)     numpy array — time axis in seconds

  State matrix row layout:
    rows 0:3   — Position [x, y, z]
    rows 3:6   — Velocity [vx, vy, vz]
    rows 6:9   — Orientation [phi, theta, psi]
    rows 9:12  — Angular velocity [p, q, r]
    rows 12:15 — Acceleration [ax, ay, az]

  Three figures produced (written to `{save_dir}`):
    1. `{save_dir}/desired_vs_actual.png` — blue (desired) vs red (actual)
       overlay for all 5 groups.
    2. `{save_dir}/errors.png`            — instantaneous error = actual − desired.
    3. `{save_dir}/cumulative_errors.png` — `time_step × cumsum(|error|)`,
       i.e. integrated absolute error in units of [unit × seconds].

  Plots are written to the `save_dir` argument passed by the caller (e.g.
  `/root/results/001/plots`). The function must NOT hardcode any path.

steps:
  - name: read-sample-rate
    description: >
      Read `sample_rate` from `/root/system_params.yaml` and derive
      `time_step = 1 / sample_rate`. Do not hardcode `time_step`.
  - name: slice-state-groups
    description: >
      Slice `state` and `state_des` into 5 groups of 3 rows each — position
      (0:3), velocity (3:6), orientation (6:9), angular velocity (9:12),
      acceleration (12:15).
  - name: compute-errors
    description: >
      For each group, compute `error = actual − desired` and
      `cumulative = time_step * np.cumsum(np.abs(error))`. The `time_step`
      factor gives cumulative error units of [unit × seconds].
  - name: build-figures
    description: >
      Create three matplotlib figures, each with a 5×3 subplot grid (5 state
      groups × 3 axes). Use `figsize=(16, 20)` to prevent label overlap. Use
      LaTeX strings for orientation labels — `r'$\phi$'`, `r'$\theta$'`,
      `r'$\psi$'`. Figure 1 overlays desired (blue) and actual (red) per axis;
      Figure 2 plots instantaneous error per axis; Figure 3 plots cumulative
      absolute error per axis.
  - name: save-figures
    description: >
      Call `os.makedirs(save_dir, exist_ok=True)`, then save each figure with
      `fig.savefig(...)` to the three filenames listed in scope_and_approval,
      and close each figure with `plt.close(fig)`.

anti_patterns:
  - Hardcoding `time_step` instead of deriving it from `sample_rate` in
    `/root/system_params.yaml`.
  - Hardcoding the output path instead of writing to the caller-supplied
    `save_dir`.
  - Omitting the `time_step` multiplier in cumulative error — the result must
    be `time_step * cumsum(|error|)`, not bare `cumsum(|error|)`.
  - Using a figsize smaller than `(16, 20)` for the 5×3 grid — labels overlap.
  - Forgetting `plt.close(fig)` after saving — leaks figure handles when
    called repeatedly.
  - Using plain ASCII labels for orientation instead of LaTeX
    (`r'$\phi$'`, `r'$\theta$'`, `r'$\psi$'`).
```
