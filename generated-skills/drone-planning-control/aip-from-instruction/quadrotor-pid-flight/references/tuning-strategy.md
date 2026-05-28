# PID tuning strategy — reference

## Defaults

Starting gains for a 1 kg quadrotor at near-hover (`scripts/tune_pid.py`):

```
kp_pos = [8.0, 8.0, 10.0]
ki_pos = [0.4, 0.4,  1.0]
kd_pos = [5.0, 5.0,  6.0]

kp_att = [60.0, 60.0, 16.0]
ki_att = [ 0.0,  0.0,  0.0]
kd_att = [ 8.0,  8.0,  4.0]
```

Rationale:
- z-axis gets a stiffer P and stronger D because gravity rejection benefits
  from higher bandwidth; the integral term cancels mass mismatch.
- Roll/pitch attitude gains dominate yaw because the rotational inertia is
  smaller around the body x/y axes for typical quads.
- Attitude integral starts at 0 — anti-windup tends to do more harm than good
  on the inner loop unless there's persistent bias.

## Search loop

The tuner runs the default once. If all four specs pass, it returns
immediately. Otherwise it does a scale-grid search over three knobs:

| Knob          | Scales tried                          |
|---------------|---------------------------------------|
| `kp_pos × sp` | `[1.0, 0.7, 1.3, 0.5, 1.6, 0.85, 1.15]` |
| `kd_pos × sd` | `[1.0, 0.7, 1.3, 0.85, 1.15]`           |
| `kp_att,kd_att × sa` | `[1.0, 0.7, 1.3, 0.85, 1.15]`     |

Stops as soon as a candidate passes all four specs; otherwise returns the
best-scoring candidate (`max(|euclid_err|) + 0.01·overshoot_pct + SSE`).

## When defaults aren't enough

Symptom → first knob to turn:

- **Steady-state offset > 0.05 m.** Increase `ki_pos` for the offending
  axis. If the axis is z, double `ki_pos[2]` to ~2.0 and re-tune.
- **Overshoot > 5%.** Increase `kd_pos` on the offending axis, or reduce
  `kp_pos`. The scale-grid covers ±30%; if you need more, edit
  `DEFAULT_GAINS` directly.
- **Per-timestep tracking error > 0.05 m during the maneuver.** Increase
  `kp_pos` *and* `kd_pos` proportionally; the scale-grid is one-axis-at-a-time
  on the position loop.
- **Roll/pitch oscillation.** Reduce attitude scale `sa` below 1.0 first; if
  oscillation persists, lower `kp_att` and increase `kd_att`.

## Re-runs

Each command file is tuned independently — gains live in
`/root/results/<id>/tuning_results.json`. Don't reuse one command's gains for
another; the search is cheap (≤ 60 evals × a few-second sim).

## Anti-patterns

- Tuning by editing the controller code instead of `DEFAULT_GAINS`. The skill
  expects gains to be a numerical input; the controller code is structural.
- Cranking integral gains for transient tracking errors. Integral fixes bias,
  not maneuver tracking. If you need better maneuver tracking, raise
  `kp_pos`/`kd_pos` first.
- Forgetting the simulation needs to extend past the commanded end time.
  Settling time and steady-state error are measured during the
  `settle_pad(T) = max(3.0, 0.5·T)` seconds after the command ends.
