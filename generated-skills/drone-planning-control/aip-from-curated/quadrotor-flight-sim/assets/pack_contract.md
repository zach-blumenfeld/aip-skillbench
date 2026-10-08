Installed simulator modules (flat .py files copied into `workdir`, importable from there):

- quad_params.py: load_params(path) -> dict. Reads system_params.yaml; inertia -> np.diag(inertia); adds dt = 1/sample_rate, T_max = 4*cT*rpm_max^2, T_min = 4*cT*rpm_min^2, twr, hover_rpm, accel_limit_up/down/horiz (yaml values win, else derived).
- flight_plan_parser.py: class FlightPlanParser; parse_flight_plan(text) -> (waypoints (4 x n) rows [x, y, z, yaw], waypoint_times (n,), modes list of n-1 strings in {'takeoff','hover','fly','land'}).
- trajectory_planner.py: class WaypointTrajectory(waypoints, waypoint_times, sample_rate, modes), each call returns (pos, quaternion, vel, acc, zeros(3)) and advances dt; trajectory_planner(waypoints, max_iter, waypoint_times, sample_rate, modes) -> (15 x max_iter) rows 0:3 pos, 3:6 vel, 6:9 [phi, theta, psi], 9:12 ang vel, 12:15 acc; max_iter_for(waypoint_times, sample_rate) = round((t_final - t0) * sample_rate) + 1; check_accel_limits(traj, params); min_feasible_duration; stretch_to_limits.
- position_controller.py: make_position_integral() -> {"e": zeros(3)}; position_controller(current_state, desired_state, params, integral) -> (F, acc). Gains read from params['kp_pos'|'ki_pos'|'kd_pos'].
- attitude_planner.py: attitude_planner(desired_state, params) -> (rot [phi_des, theta_des, psi], omega [0, 0, yaw_rate]).
- attitude_controller.py: make_attitude_integral() -> {"e": zeros(3)}; attitude_controller(current_state, desired_state, params, integral) -> M (3,). Gains from params['kp_att'|'ki_att'|'kd_att'].
- motor_model.py: prop_matrix(params); motor_model(F, M, motor_rpm, params) -> (F_actual, M_actual, rpm_dot).
- dynamics.py: dynamics(params, state16, F_actual, M_actual, rpm_motor_dot) -> state_dot (16,).
- stepinfo_3d.py: stepinfo_3d(pos_actual (3, n), pos_target (3,), t (n,), settling_threshold=0.02) -> {RiseTime, SettlingTime, Overshoot_pct, SteadyStateError}.
- plot_quadrotor.py: plot_quadrotor(state, state_des, time_vec, save_dir, params_path=None) -> writes desired_vs_actual.png, errors.png, cumulative_errors.png; sample_rate read from /root/system_params.yaml (or $QUAD_PARAMS / params_path).
- simulate.py: State(pos, vel, rot, omega, acc); simulate(waypoints, waypoint_times, modes, params, gains=None, trajectory=None) -> (actual 15xN, desired 15xN, time_vec, trajectory); plan_all, tune, run_all; CLI `python3 simulate.py --params P --commands DIR --results DIR [--tuning FILE] [--stretch]`.

Output layout written for each command file NNN.txt (label = file name without extension):
results_dir/NNN/planned_trajectory.npy   (15 x max_iter, saved right after trajectory_planner)
results_dir/NNN/metrics_3d.json          ({"mode": ..., "RiseTime", "SettlingTime", "Overshoot_pct", "SteadyStateError"})
results_dir/NNN/tuning_results.json      (same selected gains for every command: kp_pos, ki_pos, kd_pos, kp_att, ki_att, kd_att + sweep info)
results_dir/NNN/plots/{desired_vs_actual,errors,cumulative_errors}.png

Conventions: state objects carry .pos .vel .rot .omega .acc numpy arrays; gains are 3-element [x,y,z] / [phi,theta,psi] arrays applied element-wise; the vehicle starts at rest on the first trajectory sample with motors at hover RPM; each step integrates with scipy solve_ivp RK45 over [t_k, t_k+dt] with F/M held constant.
