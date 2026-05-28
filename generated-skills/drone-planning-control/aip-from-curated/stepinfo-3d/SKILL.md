---
name: stepinfo-3d
description: Use this skill when computing 3D step-response performance metrics for point-to-point drone flight — rise time, settling time, percent overshoot, and steady-state error based on Euclidean distance to the final target. Use instead of 1D stepinfo for any flight where all three position axes move simultaneously.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute step-response performance metrics — rise time, settling time, percent
  overshoot, and steady-state error — for point-to-point 3D drone flight,
  based on Euclidean distance to a fixed final target. Drop-in replacement for
  1D `stepinfo` whenever all three position axes move simultaneously, because
  per-axis metrics are misleading when thrust dynamics couple the axes.

trigger_when:
  - Evaluating drone flight performance where the commanded trajectory moves x, y, and z simultaneously (diagonal flight).
  - User asks for rise time, settling time, overshoot, or steady-state error on a 3D position trajectory.
  - 1D `stepinfo` would mislead because the axes are coupled — thrust that corrects one axis also affects the others.

do_not_use_when:
  - Flight is a pure single-axis step (hover, takeoff, land along z). Use 1D `stepinfo` on the relevant axis signal instead.
  - Trajectory is circular, figure-eight, or otherwise continuous tracking — there is no fixed convergence target. Use RMS or cumulative tracking error instead.

steps:
  - name: compute-distance-series
    description: >
      Given `pos_actual (3, n)`, `pos_target (3,)`, and time vector `t (n,)`,
      compute `dist[k] = ||pos_actual[:, k] − pos_target||₂` for every timestep.
  - name: handle-degenerate-start
    description: >
      If `dist[0] < 1e-6` the drone is already at the target (hover command).
      Short-circuit and return `RiseTime=0`, `SettlingTime=0`, `Overshoot_pct=0`,
      `SteadyStateError=0` without further computation.
  - name: rise-time
    description: >
      Scan `dist` forward in time and record the first `t[k]` where
      `dist[k] <= 0.1 * dist[0]` — the time to first reach 10% of the initial
      3D distance to target.
  - name: settling-time
    description: >
      Scan `dist` backward in time and record the last `t[k]` where
      `dist[k] > settling_threshold * dist[0]`. Default
      `settling_threshold = 0.02` (2% of initial distance).
  - name: overshoot-pct
    description: >
      After the drone first enters the settling band, track the maximum
      `dist[k]` observed thereafter. Report
      `max_post_entry / dist[0] * 100`. If the settling band is never entered,
      report `0.0` — the drone approached without oscillating past the target.
  - name: steady-state-error
    description: >
      Report `dist[-1]` — the final 3D Euclidean distance from the target,
      in metres.
  - name: return-metrics
    description: >
      Return a dict with keys `RiseTime`, `SettlingTime`, `Overshoot_pct`,
      `SteadyStateError`.

decisions:
  - signal: Pure z-axis step (hover, takeoff, land) — only one axis moves.
    action: Use 1D `stepinfo` on the `z` signal; do not call `stepinfo_3d`.
  - signal: Diagonal flight — x, y, and z all change between start and target.
    action: Call `stepinfo_3d` on the 3D Euclidean distance from the target.
  - signal: Circular or figure-eight trajectory — no single fixed convergence target.
    action: Use neither stepinfo variant; report RMS or cumulative tracking error instead.
  - signal: Initial distance `dist[0] < 1e-6` — drone is already at the target at `t[0]`.
    action: Return all four metrics as `0` without computing anything else.
  - signal: Settling band `0.02 * dist[0]` is never entered (common when initial distance is only a few cm).
    action: Report `Overshoot_pct = 0.0`; confirm by checking whether `SettlingTime` falls inside the trajectory window before treating this as proof of no overshoot.

scenarios:
  - need: Evaluate convergence quality after a diagonal point-to-point flight in a simulation.
    context: >
      The simulator returns `actual_state_matrix (state, n)` whose first three
      rows are position, plus a `waypoints` array whose last column is the
      final commanded waypoint, plus a `time_vec`.
    action: |
      Call `stepinfo_3d` on the position rows and the final waypoint:

      ```python
      from stepinfo_3d import stepinfo_3d

      pos_final_desired = waypoints[0:3, -1]   # last waypoint
      metrics = stepinfo_3d(actual_state_matrix[0:3, :], pos_final_desired, time_vec)
      for k, v in metrics.items():
          print(f'  {k}: {v:.4f}' if isinstance(v, float) else f'  {k}: {v}')
      ```
    outcome: >
      Dict with `RiseTime`, `SettlingTime`, `Overshoot_pct`, and
      `SteadyStateError` — suitable for logging or pass/fail thresholding.

anti_patterns:
  - Applying 1D `stepinfo` per axis on diagonal flight — coupled thrust dynamics make per-axis metrics misleading.
  - Calling `stepinfo_3d` on a circular or tracking trajectory; the function assumes convergence to a fixed target and will return meaningless values.
  - Defining overshoot as a single-axis crossing of the target; `stepinfo_3d` defines overshoot strictly by 3D distance growing again after the settling band is entered.
  - Treating `Overshoot_pct = 0.0` as proof of no overshoot without checking whether the settling band was ever entered (`SettlingTime` inside the trajectory window).
```
