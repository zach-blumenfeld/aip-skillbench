# Quadrotor model reference (what the installed modules implement)

## Flight-plan parsing
| Command pattern (case-insensitive) | Mode | Start waypoint if first command | End waypoint |
|---|---|---|---|
| `Take off to <h> m height in <t> seconds` | takeoff | (0, 0, 0) | (x, y, h) |
| `Hover at <h> m height for <t> seconds` | hover | (x, y, h) | (x, y, h) |
| `Fly from (<x>,<y>,<z>) to (<x'>,<y'>,<z'>) in <t> seconds` | fly | (x, y, z) | (x', y', z') |
| `Land from <h> m height in <t> seconds` | land | (x, y, h) | (x, y, 0) |
One regex per command (numeric groups only: 2 groups, or 7 for fly with optional whitespace around commas). Each command advances the time accumulator by t, pushes a COPY of its end waypoint and its mode: N waypoints, N-1 modes. Yaw row is 0 unless the plan sets it. Example: "Take off to 1 m height in 3 seconds" → waypoints [[0,0],[0,0],[0,1],[0,0]], times [0, 3], modes ['takeoff'].

## Trajectory planner
- hover: constant position (segment end waypoint), zero velocity and acceleration.
- takeoff / fly / land: clamped cubic spline (zero end velocities) over [t_start, t_end]; yaw gets its own clamped cubic. Peak accel per axis = 6·Δ/T².
- trajectory_state (15 × max_iter): rows 0:3 pos, 3:6 vel, 6:9 orientation [0, 0, yaw], 9:12 angular velocity (0), 12:15 acceleration. max_iter = round(T·sample_rate) + 1, T = waypoint_times[-1] (never hardcoded). No `question` argument — only `modes`.
- Limits (from system_params.yaml): az ≤ accel_limit_up = (T_max − m·g)/m; az ≥ −accel_limit_down = −(m·g − T_min)/m; √(ax²+ay²) ≤ accel_limit_horiz = √(T_max² − (m·g)²)/m, with T_max = 4·cT·rpm_max², T_min = 4·cT·rpm_min², twr = T_max/(m·g).

## Controllers
- Position: pos_err = cur_pos − des_pos; vel_err = cur_vel − des_vel; integral += pos_err·dt; acc = des_acc − kp·pos_err − ki·integral − kd·vel_err; F = m·(g + acc[2]).
- Attitude planner: φ_des = (ax·sinψ − ay·cosψ)/g; θ_des = (ax·cosψ + ay·sinψ)/g; rot = [φ_des, θ_des, ψ]; omega = [0, 0, desired_yaw_rate].
- Attitude controller: e = des_rot − cur_rot; integral += e·dt; M = I @ (kp·e + ki·integral + kd·(des_omega − cur_omega)).

## Motor model (X-frame, d = arm_length, cT = thrust_coefficient, cQ = moment_scale)
```
         motor:  1      2      3      4
Thrust:         +cT    +cT    +cT    +cT
Roll  (Mx):      0    +d·cT    0    -d·cT
Pitch (My):    -d·cT    0    +d·cT    0
Yaw   (Mz):    -cQ    +cQ    -cQ    +cQ
```
Solve prop_matrix @ rpm² = [F, Mx, My, Mz]; clamp negatives to 0, sqrt, clip to [rpm_min, rpm_max] (3000–20000; motors always spin); rpm_dot = km·(rpm_des − rpm_current) with km = motor_constant = 36.5 s⁻¹ (τ ≈ 27 ms); actual [F, M] = prop_matrix @ rpm_current².

## Dynamics (state 16: 0:3 pos, 3:6 vel, 6:9 [φ, θ, ψ], 9:12 [p, q, r], 12:16 motor RPM)
- ṗos = vel
- ẍ = (F/m)(cosφ·sinθ·cosψ + sinφ·sinψ); ÿ = (F/m)(cosφ·sinθ·sinψ − sinφ·cosψ); z̈ = −g + (F/m)·cosφ·cosθ  (ZYX Euler)
- Euler-angle rates = [p, q, r]; angular accel = I⁻¹ M (solve, I = np.diag(inertia)); RPM rates = rpm_dot.
- Integrate each step with `solve_ivp(..., method='RK45')` over [t_k, t_k+dt], F/M/rpm_dot held constant; new state = last column of sol.y.

## Metrics (stepinfo_3d, target = waypoints[0:3, -1])
dist[k] = ‖pos[:, k] − target‖; d0 = dist[0]; if d0 < 1e-6 → all zeros (hover starts at target). Rise time = first t with dist ≤ 0.1·d0. Settling time = last t with dist > 0.02·d0. Overshoot % = max dist after first entering the 0.02·d0 band ÷ d0 × 100 (0 if never entered). Steady-state error = dist[-1]. If dist never drops to 0.1·d0 the pack reports RiseTime = t[-1] (the source leaves this undefined). Overshoot is by distance, not by crossing the target on one axis: the vehicle must move farther from the target after entering the band; for short commands where the 0.02·d0 band is only centimetres and never entered, Overshoot_pct = 0. Assumes point-to-point flight. 1D metrics break for diagonal flight because the axes are coupled (thrust that corrects x also affects y and z). 1D stepinfo on z is the conventional choice for pure z moves, but the 3D distance reduces to |z − z_target| when x/y hold, so the pack uses stepinfo_3d for every command (file is metrics_3d.json). Circular / figure-eight paths: neither applies — use RMS or cumulative error.

## Plots (plot_quadrotor)
Three figures, each a 5 × 3 grid (pos, vel, orientation, angular velocity, acceleration × 3 axes), figsize (16, 20): desired (blue) vs actual (red); error = actual − desired; cumulative = time_step·cumsum(|error|) with time_step = 1/sample_rate read from system_params.yaml. Orientation labels r'$\phi$', r'$\theta$', r'$\psi$'. os.makedirs(save_dir, exist_ok=True), save, plt.close(fig). Never hardcode save_dir.
