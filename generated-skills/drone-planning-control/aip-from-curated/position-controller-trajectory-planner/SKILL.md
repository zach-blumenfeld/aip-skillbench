---
name: position-controller-trajectory-planner
description: Use this skill when implementing the outer control loop for a quadrotor — position PID control (position/velocity error → thrust and desired acceleration) and trajectory planning from flight-plan waypoints (takeoff, hover, fly, land segments → smooth 15-row state matrix).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Implement the quadrotor outer control loop as two cooperating modules: a
  trajectory planner that converts waypoints plus segment modes into a
  (15 × max_iter) desired-state matrix using cubic splines, and a position
  PID controller that maps position and velocity errors to thrust F and
  desired acceleration. Outputs land under /root/results/<label>/ so the
  test suite can verify the planned trajectory stays within the drone's
  physical acceleration limits at every timestep.

trigger_when:
  - Implementing the outer (position) control loop for a quadrotor.
  - Converting flight-plan waypoints (takeoff / hover / fly / land) into a smooth (15 × max_iter) state matrix.
  - Computing thrust F and desired acceleration from position/velocity errors via PID.
  - Tuning PID gains for altitude tracking, hover stability, or trajectory following.
  - Saving planned_trajectory.npy, metrics_3d.json, tuning_results.json, and plots for a drone planning-control command file.

steps:
  - name: build-trajectory-planner
    description: >
      Implement trajectory_planner(waypoints, max_iter, waypoint_times,
      sample_rate, modes) returning a (15 × max_iter) state matrix with
      rows 0:3 position, 3:6 velocity, 6:9 orientation, 9:12 angular
      velocity, 12:15 acceleration. Branch per segment mode: 'hover' holds
      constant position with zero velocity and acceleration; 'takeoff'
      fits a cubic spline from ground to target height; 'fly' fits a cubic
      spline from start position to end position; 'land' fits a cubic
      spline from current height to ground. The planner takes only the
      modes argument from the flight plan parser — never a `question`
      argument.
  - name: build-waypoint-trajectory
    description: >
      Implement WaypointTrajectory as a callable that steps through the
      cubic spline one sample at a time. In __init__, fit a CubicSpline
      over all waypoints versus their arrival times, store
      dt = 1 / sample_rate, and initialise t_current to the first waypoint
      time. On each __call__, evaluate the spline at t_current for
      position, its first derivative for velocity, and second derivative
      for acceleration; advance t_current by dt; return
      (pos, quaternion, vel, acc, zeros(3)). For non-hover segments, fit
      a separate CubicSpline over [t_start, t_end] versus
      [yaw_start, yaw_end] to interpolate yaw smoothly.
  - name: build-position-controller
    description: >
      Implement PID feedback on position and velocity errors. Compute
      pos_err = current_pos − desired_pos and
      vel_err = current_vel − desired_vel. Accumulate the integral term
      via integral_e += pos_err * dt. Compute desired acceleration as
      acc = desired_acc − kp * pos_err − ki * integral_e − kd * vel_err.
      Compute thrust F = mass * (gravity + acc[2]). Return (F, acc).
  - name: initialise-integral-state
    description: >
      Before entering the control loop, call make_position_integral() to
      produce a fresh {"e": zeros(3)} dict and pass it explicitly into the
      controller on every step. Never declare the integral as a mutable
      default argument — state would leak across calls.
  - name: read-system-params
    description: >
      Read dt = 1.0 / params['sample_rate'] from system_params.yaml, along
      with mass, gravity, and motor thrust limits T_min / T_max. Derive
      time_final = waypoint_times[-1] from the parsed flight plan. Never
      hardcode dt or time_final.
  - name: tune-gains
    description: >
      No tuning range is provided — choose PID gains freely to best
      satisfy the success criteria. Start small (e.g.
      kp_pos = [0.1, 0.1, 0.1], ki_pos = [0, 0, 0], kd_pos = [0, 0, 0])
      and increase gradually. Use the decisions table below to map
      observed symptoms to gain adjustments.
  - name: respect-acceleration-limits
    description: >
      Keep the planned trajectory's acceleration rows (12:15) within the
      drone's physical limits at every timestep: upward az ≤ 6.962 m/s²
      ((T_max − m·g) / m); downward az ≥ −9.429 m/s²
      (−(m·g − T_min) / m); horizontal √(ax² + ay²) ≤ 13.602 m/s²
      (√(T_max² − (m·g)²) / m). Exceeding any of these saturates the
      motors and tracking will fail.
  - name: save-outputs
    description: >
      For each command file (e.g. 001.txt) derive label from the filename
      without extension, set out_dir = f'/root/results/{label}', and call
      os.makedirs(out_dir, exist_ok=True). Immediately after
      trajectory_planner() returns, save the (15 × max_iter) matrix with
      np.save(os.path.join(out_dir, 'planned_trajectory.npy'),
      trajectory_matrix) — the test suite reads this file to verify the
      acceleration limits. Write metrics_3d.json containing
      {mode, RiseTime, SettlingTime, Overshoot_pct, SteadyStateError},
      tuning_results.json with the best PID gains from the sweep (same
      content for every command), and plots/ containing
      desired_vs_actual, errors, and cumulative_errors PNGs via
      plot_quadrotor(actual, desired, time_vec, save_dir=os.path.join(out_dir, 'plots')).

decisions:
  - signal: Slow altitude response.
    action: Increase kp_pos[2].
  - signal: Altitude overshoot.
    action: Increase kd_pos[2].
  - signal: Persistent altitude offset.
    action: Increase ki_pos[2].
  - signal: x/y oscillation during hover.
    action: Decrease ki_pos[0] and ki_pos[1].
  - signal: Planned trajectory acc rows exceed the physical acceleration limits.
    action: Lengthen waypoint_times or smooth the segment so motors do not saturate; the trajectory must satisfy the upward, downward, and horizontal bounds at every timestep.

anti_patterns:
  - Using a mutable default argument for the position integral — always create it with make_position_integral() before the loop and pass it explicitly.
  - Hardcoding dt instead of computing dt = 1.0 / params['sample_rate'] from system_params.yaml.
  - Hardcoding time_final instead of deriving it from waypoint_times[-1] in the parsed flight plan.
  - Passing a `question` argument to trajectory_planner — the planner only takes modes from the flight plan parser.
  - Skipping or deferring the np.save of planned_trajectory.npy after calling trajectory_planner() — the test suite needs it to check acceleration limits.
  - Writing outputs anywhere other than /root/results/<label>/ for each command file.
```
