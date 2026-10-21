# Quadrotor command-flight reference

Everything below is implemented in `scripts/drone_sim.py`. Load this when a command
failed and you must diagnose it, choose new gains, or hand-edit the library.

## Commands → waypoints (`parse_flight_plan`)

| Command pattern (case-insensitive) | Mode | Start waypoint (first command) | End waypoint |
|---|---|---|---|
| `Take off to <h> m height in <t> seconds` | `takeoff` | (0, 0, 0) | (x, y, h) |
| `Hover at <h> m height for <t> seconds` | `hover` | (0, 0, h) | (x, y, h) |
| `Land from <h> m height in <t> seconds` | `land` | (0, 0, h) | (x, y, 0) |
| `Fly from (<x>,<y>,<z>) to (<x'>,<y'>,<z'>) in <t> seconds` | `fly` | (x, y, z) | (x', y', z') |

- Output: `waypoints` (4 × n, rows x, y, z, yaw), `waypoint_times` (n,), `modes` (n−1). Each
  command pushes its **end** waypoint and one mode; time accumulates across lines.
- The start waypoint is auto-inserted on the first command only. The source parser put it
  at (0,0,0) for every command; the skill puts it where the command says the drone is,
  otherwise hover/land/fly would start with a step error far above 0.05 m.
- Numbers may be integers, decimals, or negative; whitespace around commas is optional;
  `m`/`meters`/`metres` and `s`/`sec`/`seconds` are accepted. A line that matches no
  pattern is reported as `unparsed`; never guess the numbers, rewrite it to a canonical
  form above with the same values.

## Trajectory planner (`trajectory_planner`)

- `dt = 1/sample_rate` (read from `system_params.yaml`, never hardcode 0.005);
  `time_final = waypoint_times[-1]`; `max_iter = round(time_final·sample_rate) + 1`.
- Per segment: minimum-jerk quintic s(u) = 10u³ − 15u⁴ + 6u⁵ (zero velocity and
  acceleration at both ends), peak |accel| = 5.774·|Δ|/T². The source skills used a
  clamped cubic spline (3u² − 2u³, peak 6·|Δ|/T²); its acceleration step at t=0 roughly
  doubles the tracking error on fast moves, so the quintic replaces it. `hover` is
  constant position, zero velocity and acceleration. Yaw uses its own clamped cubic
  between segment yaw endpoints.
- Acceleration limits (rows 12:15 of the plan, every timestep):
  `az ≤ accel_limit_up`, `az ≥ −accel_limit_down`, `√(ax²+ay²) ≤ accel_limit_horiz`.
  Vertical moves use min(up, down) because both an up and a down phase occur. If the
  quintic exceeds them, the planner switches that segment to a trapezoidal velocity
  profile whose acceleration sits 30 % of the way from the minimum 4·|Δ|/T² to 98 % of
  the limit (running right at the limit leaves no thrust for feedback and fails
  tracking). If even 4·|Δ|/T² does not fit, the segment is infeasible in the commanded
  time: report it, do not fake it.
- Rows: 0:3 pos, 3:6 vel, 6:9 [φ, θ, ψ] from the planned acceleration via the attitude
  planner, 9:12 [0, 0, ψ̇], 12:15 acc. Save `planned_trajectory.npy` right after planning.

## Physics (`motor_model`, `dynamics`)

- X-frame allocation (d = arm_length, cT = thrust_coefficient, cQ = moment_scale):
  ```
           motor:  1      2      3      4
  Thrust:         +cT    +cT    +cT    +cT
  Roll  (Mx):      0    +d·cT    0    -d·cT
  Pitch (My):    -d·cT    0    +d·cT    0
  Yaw   (Mz):    -cQ    +cQ    -cQ    +cQ
  ```
- Solve for squared RPM, clamp negatives to 0, sqrt, clip to [rpm_min, rpm_max];
  first-order lag `rpm_dot = km·(rpm_des − rpm)` (km = motor_constant, τ ≈ 27 ms); the
  applied force/moment come from the **current** rpm: `prop_matrix @ rpm²`.
- State (16): pos, vel, Euler [φ, θ, ψ], body rates [p, q, r], 4 motor RPMs.
  `pos' = vel`; `vel' = [0,0,−g] + (F/m)·R_zyx e3`, i.e.
  ẍ = F/m (cφ sθ cψ + sφ sψ), ÿ = F/m (cφ sθ sψ − sφ cψ), z̈ = −g + F/m cφ cθ;
  `euler' = [p, q, r]`; `omega' = I⁻¹ M`; `rpm' = rpm_dot`. Inertia is `np.diag(inertia)`.
- Integrate each control step with `scipy.integrate.solve_ivp(method='RK45')` over
  [t_k, t_k+1] with F, M, rpm_dot held constant; take the last column of `sol.y`.
- Initial state: planned start position, zero velocity/attitude, motors at hover RPM
  √(m g / 4cT).
- Thrust limits: T_max = 4 cT rpm_max², T_min = 4 cT rpm_min²; twr = T_max/(m g).

## Controllers

Position PID (outer loop):
```
pos_err = pos − pos_des;  vel_err = vel − vel_des;  integral += pos_err·dt
acc = acc_des − kp_pos·pos_err − ki_pos·integral − kd_pos·vel_err
F = m·|acc + g e3|                     # source: m·(g + acc_z), small-angle
```
Attitude planner (exact inversion of the ZYX thrust direction):
θ_des = atan2(ax cosψ + ay sinψ, g + az), φ_des = atan2((ax sinψ − ay cosψ)·cosθ_des, g + az),
ψ_des = planned yaw, ω_des = [0, 0, ψ̇_des]. For small tilts this is the source's
φ ≈ (ax sinψ − ay cosψ)/g, θ ≈ (ax cosψ + ay sinψ)/g; the small-angle form plus
F = m(g + az) gave 3–8× larger errors on diagonal flights (e.g. 0.35 m vs 0.035 m).

Attitude PID (inner loop):
```
e = rot_des − rot;  integral += e·dt
M = I @ (kp_att*e + ki_att*integral + kd_att*(omega_des − omega))   # element-wise gains, then I @
```

Design rules:
- Create both integrals fresh before each simulation (`make_position_integral()`,
  `make_attitude_integral()`); never a mutable default argument (wind-up across runs).
- Keep `ki_att ≤ 0.5`: attitude integral wind-up causes x/y oscillation during z-only moves.
- Gains are 3-vectors [x, y, z] / [φ, θ, ψ].

## Tuning

Default grid (per command, all simulated with RK45, best = passes every criterion, then
smallest max tracking error): base gains `kp_pos [12,12,16]`, `kd_pos [7,7,8]`,
`kp_att [400,400,100]`, `kd_att [40,40,20]`, all ki 0; the base itself plus position
stiffness × {1,2,3} (kd scaled by √ of that), position damping × {0.75,1,1.4}, attitude
stiffness × {0.75,1.5} (kd_att × √): 19 sets. On the reference task the winners were
kp_pos ≈ [24,24,32], kd_pos ≈ [10–14, 10–14, 11–16], kp_att 300–600. The source skills' suggested starting points
(`kp_pos 0.1`, `kp_att [100,100,50]`, zero ki/kd) are far too soft for 5 cm tracking; use
them only as a sanity floor. The retry step uses a wider grid around whatever base you give.

| Symptom | Fix |
|---|---|
| Slow altitude response | Increase `kp_pos[2]` |
| Altitude overshoot | Increase `kd_pos[2]` |
| Persistent altitude offset | Increase `ki_pos[2]` |
| x/y oscillation during hover | Decrease `ki_pos[0..1]` and `ki_att` |
| Slow roll/pitch correction (lag on fly commands) | Increase `kp_att[0..1]` |
| Roll/pitch oscillates | Increase `kd_att[0..1]` |
| Yaw drifts slowly | Increase `ki_att[2]` |
| Fly command fails tracking early in the segment | Increase `kp_att[0..1]` (faster tilt) and `kp_pos[0..1]` |
| Diverges / NaN | Attitude loop too slow for the position loop: lower `kp_pos` or raise `kp_att` |

## Metrics (`stepinfo_3d`, settling_threshold = 0.02)

On d[k] = ‖pos[:,k] − final waypoint‖:
- d[0] < 1e-6 (hover: starts at target) → all four metrics 0.
- RiseTime: first t with d ≤ 0.1·d0. SettlingTime: last t with d > 0.02·d0.
- Overshoot_pct: max d after first entering the 0.02·d0 band, as % of d0 (0 if never entered).
  Because it includes the entry sample, a clean approach reads just under 2 %.
- SteadyStateError: d[-1] in metres.
Use the 3D metric for every mode (for z-only commands it equals the 1D z metric).
`metrics_3d.json` = `{"mode": <last segment mode>, RiseTime, SettlingTime, Overshoot_pct, SteadyStateError}`.

## Success criteria per command

SteadyStateError < 0.05 m; Overshoot_pct < 5 %; planned acceleration inside the limits at
every timestep; ‖actual pos − planned pos‖ < 0.05 m at every timestep.

## Outputs per command `<results_dir>/<label>/` (label = file stem, e.g. `001`)

`metrics_3d.json`, `tuning_results.json` (six 3-float gain lists), `planned_trajectory.npy`
and `actual_trajectory.npy` (15 × max_iter; actual rows 12:15 are the simulated linear
acceleration), `plots/desired_vs_actual.png`, `plots/errors.png`,
`plots/cumulative_errors.png` (5×3 grids, figsize 16×20, blue desired / red actual,
error = actual − desired, cumulative = dt·cumsum|error|).
