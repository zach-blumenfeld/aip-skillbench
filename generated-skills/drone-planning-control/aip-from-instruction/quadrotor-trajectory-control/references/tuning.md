# Tuning Recipe

Goal: for each command, find PID gains such that
- `SteadyStateError < 0.05 m`
- `Overshoot_pct < 5`
- `max_k ‖actual[0:3, k] - planned[0:3, k]‖ < 0.05 m`

Approach: coarse-to-fine **local** search seeded by mode-specific
baselines from `baseline_gains.md`. Implemented in `scripts/tune_gains.py`.

## Cost function

```
cost = 100 * max(0, max_pos_err   - 0.05)
     + 100 * max(0, sse           - 0.05)
     +  10 * max(0, overshoot_pct - 5.0)
     +   1 * max_pos_err
```
The first three terms zero out once a criterion is satisfied; the
`+ max_pos_err` term is a tie-breaker so the optimizer keeps tightening
tracking after the hard constraints are met.

## Search

1. **Round 0 (vertical, coarse).** Multiplicative knobs `{0.5, 1.0, 2.0}`
   applied independently to `kp_pos[2]`, `kd_pos[2]`, `kp_att`, `kd_att`.
2. **Round 1 (vertical, fine).** Same knobs, `{0.75, 1.0, 1.5}`.
3. **Round 2 (horizontal).** Same factors on `kp_pos[0:2]`, `kd_pos[0:2]`.

Within each round the optimizer keeps re-scanning until no single knob
move improves the cost. Stop early as soon as all three criteria pass.

## What to do if tuning stalls

| Symptom | Likely cause | First lever |
| --- | --- | --- |
| `SteadyStateError` stuck > 0.05 in z | gravity FF missing or wrong mass | verify `a_cmd_z += g` and `T = m·|a_cmd|` |
| `Overshoot_pct > 5` in z (takeoff) | `kp_pos[2]` too aggressive | `kp_pos[2] *= 0.7`, `kd_pos[2] *= 1.3` |
| Mid-flight max-pos-err spikes during `fly` | inner attitude loop too slow | `kp_att *= 1.5`, `kd_att *= 1.2` |
| Horizontal drift in hover | yaw psi spinning | check `kp_att[2]` and `kd_att[2]`; verify mixer `tau_z` sign |
| Oscillation along z, growing amplitude | integrator windup or dt too large | drop `ki_pos[2]` to 0; cut `dt` to 0.005 s |
| Per-timestep error fine but Overshoot OK fails | metrics computed on wrong axis | confirm scalar response choice in `metrics._scalar_response` |

## Diagnostic — when the optimizer can't fix it

If after Round 2 the cost is still > 50, the issue is structural, not
gain-tuning. Check, in order:
1. Planned trajectory exceeds accel limits at some `k` —
   `planner.PlanResult.extended` should be True if `T_req` was too
   short; if you bypassed the planner, accel-limit violation will show
   here.
2. Mixer / dynamics motor-direction mismatch — see
   `dynamics_reference.md`. Symptom: yaw spins or sign of one torque
   reversed; controller fights itself.
3. Initial state placed away from `planned[0:3, 0]` — first-tick error
   blows past 0.05 m before tracking starts. Set `init_state[0:3] =
   planned[0:3, 0]` exactly.
