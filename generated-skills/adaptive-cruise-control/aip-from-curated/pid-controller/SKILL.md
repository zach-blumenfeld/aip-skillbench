---
name: pid-controller
description: Use this skill when implementing PID control loops for adaptive cruise control, vehicle speed regulation, throttle/brake management, or any feedback control system requiring proportional-integral-derivative control.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Implement a discrete-time PID (Proportional–Integral–Derivative) feedback
  controller for closed-loop regulation — speed, position, distance, or any
  signal where a setpoint is tracked against a measured value. Covers the
  control law, the per-step compute() method, anti-windup, output clamping,
  derivative filtering, and a manual tuning procedure used to hit rise time,
  overshoot, and steady-state error targets.

trigger_when:
  - Implementing a PID control loop in code.
  - Writing speed, distance, position, or attitude controllers.
  - Building adaptive cruise control, vehicle speed regulation, throttle/brake control, or any feedback regulator.
  - Tuning an existing PID for rise time, overshoot, or steady-state error.
  - User mentions PID, proportional/integral/derivative gains, Kp/Ki/Kd, feedback control, or setpoint tracking.

do_not_use_when:
  - The system is open-loop (no feedback signal) — use a feed-forward map instead.
  - The system needs model-predictive or state-space control (MPC, LQR) — PID is the wrong tool when constraints or multi-variable coupling dominate.
  - The plant is already controlled and the task is only higher-level setpoint scheduling.

steps:
  - name: identify-loop-spec
    description: >
      Identify the loop variables before writing code: setpoint, measured signal,
      error sign convention (conventionally `error = setpoint - measured`),
      actuator output range (e.g. acceleration limits), timestep `dt`, and the
      performance targets (rise time, overshoot, steady-state error). Confirm
      output saturation limits up front — they determine whether anti-windup is
      required and what `integral_max` should be.
    outputs:
      - name: loop-spec
        type: object
        description: setpoint, error sign, dt, output_min/output_max, targets

  - name: install-pid-template
    description: >
      Install the reference implementation from `assets/pid_controller.py` to the
      project root as `pid_controller.py`. The template provides the required
      positional constructor `__init__(kp, ki, kd)` plus keyword-only saturation
      knobs (`output_min`, `output_max`, `integral_max`), `reset()`, and
      `compute(error, dt) -> float`. Do not strip the anti-windup clamping or the
      derivative low-pass filter — both are load-bearing for stable control.
    script: scripts/install_template.py
    inputs:
      - name: loop-spec
        type: object
    outputs:
      - name: pid-module-path
        type: string

  - name: choose-anti-windup
    description: >
      Anti-windup is required whenever the output saturates against output_min or
      output_max for sustained periods. Without it, the integrator keeps growing
      during saturation and the loop overshoots wildly after the actuator
      desaturates. Pick one strategy:
        - integral-clamping (template default): pass `integral_max` so that
          `ki * integral_max` is roughly the actuator range. Simple and robust;
          start here.
        - conditional-integration: skip the `self.integral += error * dt` update
          whenever the output is at a limit. Useful when the actuator stays
          saturated for long stretches.
        - back-calculation: subtract a fraction of the saturation overshoot
          (pre-clamp output minus post-clamp output) from the integrator each
          step. Best for tight tracking near the limit; introduces an extra
          tuning gain.
    inputs:
      - name: pid-module-path
        type: string
    one_of:
      - integral-clamping
      - conditional-integration
      - back-calculation

  - name: wire-output-clamping
    description: >
      Pass the actuator range as `output_min`/`output_max` to the constructor so
      `compute()` returns physically realizable values. For ACC throttle/brake,
      that is the acceleration range, e.g. `output_min=-8.0, output_max=3.0`.
      Clamping downstream of the PID (without telling the PID) is what causes
      integrator windup — always clamp inside the controller.
    inputs:
      - name: loop-spec
        type: object

  - name: tune-gains
    description: >
      Manual tuning, one gain at a time. Start with Ki = Kd = 0. Increase Kp
      until the closed-loop response is fast enough but still stable. Add Ki to
      drive steady-state error toward zero — too high causes slow oscillation.
      Add Kd to damp overshoot and ringing — too high amplifies measurement
      noise. Re-run the closed-loop simulation between adjustments and read off
      rise time, overshoot, and steady-state error. Persist the chosen gains in
      the surrounding system's config (e.g. a `tuning_results.yaml` with
      `kp`, `ki`, `kd` per loop).

      Qualitative effects:
        - Higher Kp → faster response, more overshoot, can destabilize.
        - Higher Ki → eliminates steady-state error, slower settling, oscillation risk.
        - Higher Kd → damps overshoot, amplifies sensor noise.
    inputs:
      - name: loop-spec
        type: object
    outputs:
      - name: tuned-gains
        type: object
        description: kp, ki, kd for this loop

  - name: validate-loop
    description: >
      Run the closed-loop simulation with the tuned gains and check against the
      performance targets in loop-spec. If a target misses, return to
      tune-gains — do not relax the target silently. If the loop oscillates at
      the limit cycle, anti-windup is wrong or Kd is too low.
    inputs:
      - name: tuned-gains
        type: object
      - name: loop-spec
        type: object
    outputs:
      - name: performance-report
        type: object

scenarios:
  - need: ACC speed loop tracking a 30 m/s setpoint with acceleration limits [-8.0, 3.0] m/s² and a 0.1 s timestep.
    context: Initial gains Kp=0.1, Ki=0.01, Kd=0 leave rise time well above the 10 s target and a nonzero steady-state error.
    action: >
      Install the template with `output_min=-8.0`, `output_max=3.0`,
      `integral_max≈10`. Raise Kp toward ≈0.8 for response speed, add
      Ki≈0.15 to eliminate steady-state error, add Kd≈0.1 to damp overshoot.
      `reset()` the controller on mode entry.
    outcome: Rise time < 10 s, overshoot < 5%, steady-state speed error < 0.5 m/s.
  - need: ACC follow-distance loop holding `safe_distance = v_ego * t_headway + d_min` behind a lead vehicle.
    context: Error is `distance - safe_distance` (positive = too far back); units are meters so the integrator term lives on a different scale than the speed loop.
    action: >
      Install the template with the same actuator limits as the speed loop and
      a larger `integral_max` (≈20). Tune Kp≈0.5, Ki≈0.08, Kd≈0.15. Add a
      feed-forward term outside the PID (e.g. proportional to lead/ego speed
      difference) so the loop reacts to lead-vehicle accelerations without
      relying on integrator buildup.
    outcome: Distance steady-state error < 2 m, minimum gap respected, smooth follow ↔ cruise transitions.

anti_patterns:
  - Clamping the actuator command downstream of the PID without telling the PID — the integrator winds up during saturation and the loop overshoots violently when it desaturates. Always set output_min/output_max on the controller.
  - Letting the integral accumulate during long output saturation. Use integral_max, conditional integration, or back-calculation.
  - Differentiating a noisy raw signal with no filter. Kd amplifies measurement noise; keep the template's derivative low-pass filter or compute the derivative on the measurement instead of the error to avoid derivative kick on setpoint changes.
  - Dividing by `dt` without guarding `dt > 0`. Produces NaN/inf on the first step or on a paused loop. The template returns 0.0 when dt <= 0.
  - Forgetting to call `reset()` on mode changes (cruise → follow → emergency). Stale integrator state injects a step disturbance the moment the controller takes over.
  - Tuning all three gains at once. Use the Kp → Ki → Kd order so each adjustment's effect on rise time, steady-state error, and overshoot is legible.
  - Hard-coding gains in source. Read tuned gains from the surrounding system's config file (e.g. tuning_results.yaml) so the simulation can iterate on tuning without code changes.
```
