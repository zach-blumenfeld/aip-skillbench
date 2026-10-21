# Model reference: physics, control, planning, metrics, plots

Load this when changing or explaining the simulator. The scripts already implement everything here.

## Parameters (`system_params.yaml`)

`sample_rate` (Hz, dt = 1/sample_rate), `mass`, `gravity`, `arm_length` d, `thrust_coefficient` c_T, `moment_scale` c_Q (yaw torque coefficient), `motor_constant` k_m, `rpm_min`, `rpm_max`, `inertia` (3 diagonal elements → `np.diag`), and `accel_limit_up/down/horiz`. `motor_spread_angle` and `COM_vertical_offset` are present but unused by this model.

Derived limits (they must match the yaml values):
- T_max = 4·c_T·rpm_max², T_min = 4·c_T·rpm_min², thrust-to-weight = T_max/(m·g)
- accel_limit_up = (T_max − m·g)/m; accel_limit_down = (m·g − T_min)/m; accel_limit_horiz = √(T_max² − (m·g)²)/m
- With the reference yaml: 6.962, 9.429, 13.602 m/s². Hover RPM = √(m·g/(4·c_T)) ≈ 15 300.

| Motor limit | Value | Meaning |
|---|---|---|
| rpm_min | 3000 | motors always spinning |
| rpm_max | 20000 | max motor speed |
| motor_constant k_m | 36.5 s⁻¹ | first-order lag, τ = 1/k_m ≈ 27 ms |

## Motor model (`quad_model.motor_model`)

The X-frame allocation maps squared RPM to [F, Mx, My, Mz]:
```
         motor:  1      2      3      4
Thrust:         +cT    +cT    +cT    +cT
Roll  (Mx):      0    +d·cT    0    -d·cT
Pitch (My):    -d·cT    0    +d·cT    0
Yaw   (Mz):    -cQ    +cQ    -cQ    +cQ
```
1. Solve `prop_matrix @ rpm_sq = [F, Mx, My, Mz]`.
2. Clamp negatives to 0, take the sqrt, clip to [rpm_min, rpm_max].
3. Lag: `rpm_dot = k_m·(rpm_des − rpm_current)`.
4. Actual `[F, M] = prop_matrix @ rpm_current²`. Return `(F_actual, M_actual, rpm_dot)`.

## Dynamics (`quad_model.dynamics`), state (16,)

0:3 position, 3:6 velocity, 6:9 Euler [φ, θ, ψ] (ZYX), 9:12 angular velocity [p, q, r], 12:16 motor RPM.
- ṗ = v
- v̇x = (F/m)(cosφ sinθ cosψ + sinφ sinψ); v̇y = (F/m)(cosφ sinθ sinψ − sinφ cosψ); v̇z = −g + (F/m) cosφ cosθ
- Euler rates = [p, q, r] (simplified model); ω̇ = I⁻¹ M (`np.linalg.solve`)
- RPM derivative = rpm_dot from the motor model

Integration: per control step, `solve_ivp(method='RK45')` over [t_k, t_{k+1}]. F_actual, M_actual and rpm_dot are held constant for the step, and the last column of `sol.y` is the new state. The gain search uses an equivalent fixed-step RK4 for speed. Final outputs always use RK45.

Actual-trajectory rows 12:15 hold the true acceleration v̇ at each sample.

## Control loop (one iteration)

```
F, acc = position_controller(pos, vel, des_pos, des_vel, des_acc, gains, params, pos_int)
rot_des, omega_des = attitude_planner(acc, current_yaw, des_yaw, des_yaw_rate, params)
M = attitude_controller(rot, omega, rot_des, omega_des, gains, params, att_int)
F_act, M_act, rpm_dot = motor_model(F, M, rpm, params)
state = integrate(dynamics, state, F_act, M_act, rpm_dot)
```
- Position PID: `pos_err = cur − des`, `vel_err = cur − des`, `integral += pos_err·dt`, `acc = des_acc − kp∘pos_err − ki∘integral − kd∘vel_err`, `F = m(g + acc_z)`.
- Attitude planner (small angle): φ_des = (ax sinψ − ay cosψ)/g, θ_des = (ax cosψ + ay sinψ)/g, `omega_des = [0, 0, yaw_rate_des]`.
- Attitude PID: `e = rot_des − rot`, `integral += e·dt`, `M = I @ (kp∘e + ki∘integral + kd∘(omega_des − omega))`. Gains are element-wise per axis [φ, θ, ψ] and are applied before the inertia matrix product.
- Tilt-compensated variant (`tilt_comp=True`): F = m·‖acc + g·e_z‖. In the yaw frame, f = (fx, fy, g + az), θ = atan2(fx, fz), φ = atan2(−fy, √(fx² + fz²)). This matches the small-angle law for small tilts.

Built-in starting gains (`run_commands.DEFAULT_GAINS`): kp_pos [20, 20, 30], ki_pos 0, kd_pos [8, 8, 10], kp_att [900, 900, 200], ki_att 0, kd_att [60, 60, 30]. The sources suggested starting from much smaller gains (kp_pos 0.1, kp_att [100, 100, 50]) and increasing them. Gains that low cannot meet the 5 cm bound. The search explores each gain group multiplicatively within 0.2×–5× of the start gains, plus additive ki_pos steps.

## Planner (`trajectory_planner.py`)

- Modes: `hover` holds the position with zero velocity and acceleration. `takeoff`, `fly` and `land` use a clamped cubic per segment (zero velocity at both ends). Yaw gets its own clamped cubic over [t_start, t_end].
- If 6·L/T² exceeds the directional limit, the segment instead accelerates at a1, coasts, then brakes at a2 along the straight line. a1 and a2 are scaled to their own directional limits: speed-up uses `up` for climbs and `down` for descents, and braking uses the opposite one. `horiz` divided by the horizontal fraction of the path is also applied. The scale is the minimum feasible plus 2%.
- Rows 6:8 hold the roll/pitch that would produce the planned acceleration. Rows 9:11 are their numerical derivatives, and row 11 is the yaw rate.
- `WaypointTrajectory()` called repeatedly returns `(pos, quaternion, vel, acc, zeros(3))` and advances by dt.

## Metrics (`stepinfo_3d.py`)

dist_k = ‖pos_k − target‖, d0 = dist_0, target = final waypoint.
- d0 < 1e-6 (hover): rise, settling and overshoot are 0, and SSE = dist_end.
- RiseTime: first t with dist ≤ 0.1·d0.
- SettlingTime: last t with dist > threshold·d0 (threshold 0.02).
- Overshoot_pct: max dist after the first entry into the band, ×100/d0. It is 0 if the band is never entered.
- SteadyStateError: dist at the final sample.

When to use which metric: 1D stepinfo on z suits pure z moves, `stepinfo_3d` suits any move (it equals the 1D version for pure z), and circular or figure-eight paths need RMS or cumulative error. 1D metrics break for diagonal flight because the axes are coupled. The task's schema always uses `stepinfo_3d`.

## Plots (`plot_quadrotor.py`)

Three 5×3 grids (figsize 16×20): position, velocity, orientation (φ, θ, ψ labels in LaTeX), angular velocity, acceleration × 3 axes. `desired_vs_actual.png` plots desired in blue against actual in red. `errors.png` plots actual − desired. `cumulative_errors.png` plots time_step·cumsum(|error|), with time_step = 1/sample_rate read from the yaml. The folder is created with `os.makedirs(save_dir, exist_ok=True)`, and each figure is closed after saving.
