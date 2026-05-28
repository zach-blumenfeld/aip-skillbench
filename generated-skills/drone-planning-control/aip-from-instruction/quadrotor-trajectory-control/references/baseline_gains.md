# Baseline Gains by Command Mode

These are starting points for `scripts/tune_gains.py`. They assume a
~1 kg quadrotor with `arm_length ≈ 0.17 m`, `Ixx,Iyy ≈ 0.01`,
`Izz ≈ 0.02`, and `g = 9.81`. Scale proportionally if mass or inertia
differ by more than 2x.

## takeoff / land / hover (vertical-dominant)
```
kp_pos = [4.0,  4.0,  8.0]
ki_pos = [0.0,  0.0,  0.5]    # small z-integrator helps reject thrust bias
kd_pos = [3.0,  3.0,  5.0]
kp_att = [200., 200., 80.]
ki_att = [0.0,  0.0,  0.0]
kd_att = [20.,  20.,  10.]
```

## fly (3-D point-to-point)
```
kp_pos = [6.0,  6.0,  8.0]    # stronger horizontal restoring
ki_pos = [0.0,  0.0,  0.0]
kd_pos = [4.0,  4.0,  5.0]
kp_att = [250., 250., 80.]    # faster inner loop to track tilt demand
ki_att = [0.0,  0.0,  0.0]
kd_att = [22.,  22.,  10.]
```

## Tuning order (`tune_gains.py` enforces this)
1. **Round 0 — coarse, vertical.** Scale `kp_pos[2]`, `kd_pos[2]`,
   `kp_att`, `kd_att` by {0.5, 1.0, 2.0}.
2. **Round 1 — fine, vertical.** Same knobs, {0.75, 1.0, 1.5}.
3. **Round 2 — horizontal.** Scale `kp_pos[0:2]`, `kd_pos[0:2]` by
   {0.75, 1.0, 1.5}.

Stop early as soon as all three criteria pass:
`sse<0.05`, `overshoot_pct<5`, `max_pos_err<0.05`.

## When to introduce integrator gains
- Only after kp/kd are stable.
- Use `ki_pos[2] ≤ 0.5` for sustained hovers (>5 s).
- For short maneuvers (<2 s), leave all `ki` at 0 — windup dominates.
- Add anti-windup clamps if you raise `ki` above 1.

## Sanity values
- Hover thrust per motor: `m·g/4 ≈ 2.45 N` at m=1 kg. If your
  `max_thrust_per_motor` is below ~5 N, the drone can't accelerate
  upward; check the YAML.
- Inner attitude loop must run >5× faster than the outer position loop
  for cascade stability. `dt = 0.005 s` (200 Hz) gives 200 Hz on both,
  which is usually enough because the controller is computed every tick.
