---
name: pid-controller
description: Use this skill when implementing PID control loops for adaptive cruise control, vehicle speed regulation, throttle/brake management, or any feedback control system requiring proportional-integral-derivative control.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Implement a discrete-time PID feedback controller — proportional + integral
  + derivative on the error signal — with output clamping and an explicit
  anti-windup choice, then tune the three gains. The canonical control law is
  `output = Kp*error + Ki*integral(error) + Kd*derivative(error)` where
  `error = setpoint - measured_value`. Covers vehicle speed regulation,
  distance/headway control, throttle/brake actuation, and any single-loop
  feedback system with one measured variable.

trigger_when:
  - Implementing adaptive cruise control (ACC) speed or distance loops.
  - Building throttle/brake or steering actuator control on a vehicle.
  - Writing any feedback control loop with a setpoint and a measured signal.
  - User asks for a PID, PI, PD, or P controller, or mentions gains Kp/Ki/Kd.
  - User asks to tune an existing controller that is slow, overshooting, oscillating, or has steady-state error.

do_not_use_when:
  - The plant is open-loop only — there is no measured feedback to act on.
  - A more advanced controller is explicitly required (MPC, LQR, gain-scheduled, adaptive).
  - The task is pure signal filtering, not closed-loop control.

steps:
  - name: emit-pid-class
    description: >
      Write the canonical discrete-time PID class to the target module path
      (e.g. `pid_controller.py`). The emitted class exposes
      `__init__(kp, ki, kd, output_min=None, output_max=None)`,
      `reset()`, and `compute(error, dt)`. P uses the current error, I uses
      rectangular accumulation `integral += error * dt`, D uses the backward
      difference `(error - prev_error) / dt` guarded against `dt <= 0`, and
      the sum is clamped to `[output_min, output_max]` when provided.
    script: scripts/emit_pid_controller.py
    inputs:
      - name: output_path
        type: string
        description: Destination .py path to write the PID controller to.
    outputs:
      - name: pid_module_path
        type: string

  - name: choose-anti-windup
    description: >
      Pick an anti-windup strategy and apply it to the controller. Windup
      happens when the output saturates (hits `output_min`/`output_max`) but
      the integral keeps accumulating, leaving the loop slow to recover when
      the error reverses. See `references/anti-windup.md` for code shapes
      and selection guidance. For ACC speed loops with `[-8.0, 3.0] m/s^2`
      actuator limits, conditional integration is the default.
    one_of:
      - clamping
      - conditional-integration
      - back-calculation
    outputs:
      - name: anti_windup_strategy
        type: string

  - name: tune-gains
    description: >
      Manual-tune in the canonical order. Run `tuning_advisor.py --procedure`
      for the order, `--effects` for what each gain does, and
      `--symptom NAME` to map an observed closed-loop symptom (overshoot,
      oscillation, steady-state-error, slow-response, noise-amplification,
      windup) to which gain to adjust and in which direction. For the ACC
      task, persist final gains to `tuning_results.yaml` as `pid_speed` and
      `pid_distance` blocks with `kp`, `ki`, `kd` each.
    script: scripts/tuning_advisor.py
    inputs:
      - name: symptom
        type: string
        nullable: true
        description: Observed closed-loop symptom name, or omit and pass `--procedure`/`--effects`.
    outputs:
      - name: advice
        type: object
        description: "{adjust: 'kp'|'ki'|'kd', direction: 'increase'|'decrease'|'anti-windup', reason: string}, plus optional procedure/effects."

scenarios:
  - need: ACC speed loop is tracking the 30 m/s setpoint but settles ~1.2 m/s low.
    context: Symptom is steady-state error — the integral term is not pulling the output up.
    action: Run `tuning_advisor.py --symptom steady-state-error`; increase Ki in small steps until the residual error closes without inducing oscillation.
    outcome: Steady-state error drops below the 0.5 m/s target.

  - need: ACC distance loop overshoots the desired headway and oscillates around it.
    context: Symptom is oscillation, likely from excess Ki interacting with actuator saturation.
    action: Lower Ki and switch the integral to conditional integration per `references/anti-windup.md`.
    outcome: Distance settles within the 2 m steady-state-error budget and respects the 5 m minimum gap.

  - need: Initial response from 0 m/s is sluggish — rise time exceeds 10 s.
    context: Kp is too low; D and I are off so the response is purely proportional.
    action: Raise Kp until rise time meets the target, watching for overshoot before re-introducing Kd.
    outcome: Rise time falls under 10 s with overshoot still under 5 percent.

anti_patterns:
  - Letting the integral accumulate while the output is saturated — classic windup.
  - Dividing by `dt` for the derivative without guarding `dt > 0`.
  - Tuning all three gains together before observing P-only behavior in isolation.
  - Differentiating a raw noisy sensor signal — Kd amplifies the noise; filter first or lean on P+I.
  - Reusing one controller instance across independent runs without calling `reset()`.
  - Embedding tuned gains as literals inside the controller — load them from a config (e.g. `tuning_results.yaml`).
  - Treating clamping the *output* as anti-windup — output clamps alone do not stop the integral from accumulating.
```
