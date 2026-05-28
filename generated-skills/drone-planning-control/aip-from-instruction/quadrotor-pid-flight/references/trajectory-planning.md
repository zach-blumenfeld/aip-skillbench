# Trajectory planning — reference

## Profile choice

The task asks for **time-parameterized piecewise continuous trajectories**
that stay within physical acceleration limits.

Use a **quintic minimum-jerk polynomial** between rest-to-rest endpoints:

```
s(τ)   = 10 τ³ − 15 τ⁴ + 6 τ⁵                 τ = t / T  ∈ [0, 1]
ṡ(τ)  = 30 τ² − 60 τ³ + 30 τ⁴
s̈(τ)  = 60 τ − 180 τ² + 120 τ³
```

Properties:
- `s(0)=0, s(1)=1`
- `ṡ(0)=ṡ(1)=0`, `s̈(0)=s̈(1)=0` — C² at both endpoints
- Peak `|s̈|` at τ=0.5: `s̈_max = 10/√3 ≈ 5.7735`

A position trajectory from `p₀` to `p₁` over duration `T`:

```
p(t)  = p₀ + (p₁ − p₀) · s(t/T)
v(t)  = (p₁ − p₀) · ṡ(t/T) / T
a(t)  = (p₁ − p₀) · s̈(t/T) / T²
```

## Per-mode planning

| Mode    | `p₀`            | `p₁`             | Notes                              |
|---------|-----------------|------------------|------------------------------------|
| takeoff | (0, 0, 0)       | (0, 0, h)        | vertical step                      |
| land    | (0, 0, h)       | (0, 0, 0)        | descent — uses `accel_limit_down`  |
| hover   | (0, 0, h)       | (0, 0, h)        | constant; no motion                |
| fly     | (x, y, z)       | (x', y', z')     | full 3-D; uses all three limits    |

For hover, the trajectory is constant. The simulator and tuner still need a
horizon — pad with `settle_pad(T) = max(3.0, 0.5·T)` seconds beyond the
commanded duration so settling can be measured.

## Acceleration-limit check

Peak per-axis accel for the quintic over `T`:

```
a_peak_axis = 5.7735 · |Δp_axis| / T²
a_peak_horiz = 5.7735 · ||Δp_horiz|| / T²
a_peak_z     = 5.7735 · |Δz| / T²
```

Compare against:
- `accel_limit_horiz` for horizontal components
- **Both** `accel_limit_up` and `accel_limit_down` for the z component —
  the quintic has *equal* positive and negative accel peaks (acceleration
  phase then deceleration phase), so any vertical move uses both limits
  regardless of its net direction.

Since `a_peak ∝ 1/T²`, the smallest feasible duration is:

```
T_min = T · sqrt( max(a_peak_horiz / accel_limit_horiz,
                      a_peak_z     / z_limit_used,
                      1.0) )
```

The planner raises a clear error if the requested `T` would violate any limit
and reports `T_min_required`. Don't silently extend duration — the agent may
need to re-pose the question with the user.

## Filling the 15-row matrix

```
rows 0:3   = position(t)         from the quintic
rows 3:6   = velocity(t)         from the quintic
rows 6:9   = [0, 0, 0]           planner does NOT set attitude; the cascaded
                                 controller derives roll/pitch from the
                                 acceleration demand
rows 9:12  = [0, 0, 0]           same
rows 12:15 = acceleration(t)     from the quintic
```

Setting orientation/angular-velocity rows to 0 is intentional and correct.
Position + velocity + acceleration uniquely specify the cascaded controller's
reference; tying down roll/pitch on top of that would over-constrain the
problem.
