# PID tuning guide (position + attitude loops)

Both loops: gains are 3-element arrays, multiplied element-wise (never matrix-multiplied) before the inertia `@` in the attitude law. `dt = 1/sample_rate` from system_params.yaml — never hardcode 0.005.

Starting values from the source skills (deliberately weak; increase gradually):
- position: kp_pos = [0.1, 0.1, 0.1], ki_pos = [0, 0, 0], kd_pos = [0, 0, 0]
- attitude: kp_att = [100, 100, 50], ki_att = [0, 0, 0], kd_att = [0, 0, 0]

No tuning range is prescribed: choose gains freely to best satisfy the success criteria. The pack's sweep parameterises both loops as second-order systems: position kp = wn², kd = 2·zeta·wn; attitude kp = wa², kd = 2·zeta·wa (yaw at wa/2). On the reference vehicle (m = 0.770 kg, motor lag tau = 1/36.5 s ≈ 27 ms) wn ≈ 6, wa ≈ 24, zeta = 1 tracked every command to millimetres; wn ≥ 7 with wa ≥ 24 and zeta = 0.8 went unstable — keep the attitude loop ≳ 3× faster than the position loop and below the motor bandwidth.

## Position loop symptoms
| Symptom | Fix |
|---|---|
| Slow altitude response | Increase `kp_pos[2]` |
| Altitude overshoot | Increase `kd_pos[2]` |
| Persistent altitude offset | Increase `ki_pos[2]` |
| x/y oscillation during hover | Decrease `ki_pos[0]` and `ki_pos[1]` |

## Attitude loop symptoms
| Symptom | Fix |
|---|---|
| Slow roll/pitch correction | Increase `kp_att[0]` or `kp_att[1]` |
| Roll/pitch oscillates | Increase `kd_att[0]` or `kd_att[1]` |
| Yaw drifts slowly | Increase `ki_att[2]` |
| x/y oscillation during hover | Decrease `ki_att` |

## Rules
- Attitude ki ≤ 0.5: attitude integral wind-up causes x/y oscillations during z-only manoeuvres.
- Integrals live in dicts made by `make_position_integral()` / `make_attitude_integral()` once per simulation run, before the loop, and are passed explicitly. A mutable default argument winds up across runs (the sweep runs many simulations in one process).
- If the planned trajectory asks for more than the acceleration limits, the motors saturate and no gains will make tracking succeed — fix the plan, not the gains.

## Reading the metrics
- Overshoot_pct counts the largest distance AFTER first entering the 2% band, entry point included, so a clean, non-oscillating approach reads about 1.9–2.0%. Do not retune to push it below 2%. Values well above 2% mean real oscillation or overshoot.
- Hover commands start on the target, so stepinfo_3d returns zeros. Judge hover drift by `TrackingRMS` and `max_abs_xy_error` in the run summary.
- SteadyStateError is measured at time_final, the moment the trajectory arrives. It is tracking lag, so it shrinks with a stiffer position loop and higher kd, not with ki.
