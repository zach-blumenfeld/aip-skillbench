# Anti-Windup Strategies

Integral windup occurs when the controller's output saturates (hits its min
or max clamp) but the integral term keeps accumulating error. When the error
finally changes sign, the accumulated integral takes a long time to unwind,
leaving the controller sluggish or causing large overshoot.

Three standard mitigations, in increasing complexity:

## 1. Clamping (integral magnitude limit)

Bound the integral term itself to a fixed range:

```python
self.integral = max(min(self.integral, I_MAX), I_MIN)
```

Simplest to add. Pick I_MAX/I_MIN so that `Ki * integral` cannot exceed the
output clamp range on its own.

## 2. Conditional Integration

Only accumulate the integral when the output is NOT saturated, or when
integrating would move the output back into the unsaturated range:

```python
unsaturated = self.output_min is None or self.output_min < output < self.output_max
moving_back = (output >= self.output_max and error < 0) or \
              (output <= self.output_min and error > 0)
if unsaturated or moving_back:
    self.integral += error * dt
```

Good default for ACC speed/distance loops — easy to reason about, no extra
gain to tune.

## 3. Back-Calculation

When the output is clamped, reduce the integral by an amount proportional to
the saturation excess, via a back-calculation gain Kb:

```python
unclamped = p_term + i_term + d_term
clamped = clip(unclamped, output_min, output_max)
self.integral += Kb * (clamped - unclamped) * dt
```

Smoothest unwinding behavior but adds a tuning parameter. Reach for it when
clamping or conditional integration leave visible response artifacts.

## Picking a strategy

- ACC speed loop with `[-8.0, 3.0]` m/s^2 actuator limits: **conditional integration** is sufficient.
- Distance loop where the lead vehicle disappears/reappears: **conditional integration** plus a `reset()` on mode transitions.
- Tight overshoot budgets after long saturation: consider **back-calculation**.
