---
name: simulation-metrics
description: Use this skill when calculating control system performance metrics such as rise time, overshoot percentage, steady-state error, or settling time for evaluating simulation results.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Evaluate the step-response of a control system from time-series simulation
  results against a target setpoint. Provides four canonical metrics — rise
  time, overshoot percentage, steady-state error, and settling time — with
  the standard definitions used in control-engineering analysis (10–90% rise
  band, peak-vs-target overshoot, final-fraction averaging for SS error,
  ±2% settling tolerance by default).

trigger_when:
  - Calculating rise time, overshoot, steady-state error, or settling time from simulation output.
  - Evaluating a control system's step response or transient performance.
  - User asks how well a controller tracks a setpoint or compares a response against a target.
  - Reporting performance metrics for a simulation run (e.g., adaptive cruise control, PID tuning).

do_not_use_when:
  - The simulation has no clear scalar target setpoint (use a different evaluation approach).
  - The signal is not a step response (these definitions assume a step-like target).

steps:
  - name: load-series
    description: >
      Extract parallel time and value sequences from the simulation results and
      identify the target setpoint. `times` and `values` must be the same length
      and ordered by ascending time.
    outputs:
      - name: times
        type: list[float]
        description: Monotonically increasing sample times.
      - name: values
        type: list[float]
        description: Measured response values, aligned with `times`.
      - name: target
        type: float
        description: The setpoint the controller is tracking.

  - name: compute-metrics
    description: >
      Call `all_metrics(times, values, target)` from `scripts/metrics.py` to
      compute all four metrics in one pass. For one-off use, the individual
      functions (`rise_time`, `overshoot_percent`, `steady_state_error`,
      `settling_time`) are also importable. CLI form:
      `python scripts/metrics.py --json '{"times": [...], "values": [...], "target": 30.0}'`.
    script: scripts/metrics.py
    inputs:
      - name: times
        type: list[float]
      - name: values
        type: list[float]
      - name: target
        type: float
      - name: final_fraction
        type: float
        nullable: true
        description: Optional. Fraction of trailing samples used for steady-state averaging. Defaults to 0.1.
      - name: tolerance
        type: float
        nullable: true
        description: Optional. Settling-band half-width as a fraction of target. Defaults to 0.02 (±2%).
    outputs:
      - name: rise_time
        type: float
        nullable: true
        description: Time from 10% to 90% of target. Null if either threshold is never crossed.
      - name: overshoot_percent
        type: float
        description: Peak overshoot above target as a percentage of target. 0.0 if peak ≤ target.
      - name: steady_state_error
        type: float
        description: Absolute error between target and mean of the final `final_fraction` of samples.
      - name: settling_time
        type: float
        nullable: true
        description: First time after which the response stays within ±tolerance·target. Null if it never settles.

  - name: report
    description: >
      Present the four metrics together. Report units consistent with the
      simulation (seconds for times, percent for overshoot, same units as the
      target for steady-state error). Preserve nulls when rise time or
      settling time is undefined — do not substitute 0.
    inputs:
      - name: rise_time
        type: float
        nullable: true
      - name: overshoot_percent
        type: float
      - name: steady_state_error
        type: float
      - name: settling_time
        type: float
        nullable: true

scenarios:
  - need: Evaluate a cruise-control simulation that holds 30 m/s with results as a list of `{time, value}` rows.
    action: >
      Build `times = [row['time'] for row in results]` and
      `values = [row['value'] for row in results]`, set `target = 30.0`, then
      call `all_metrics(times, values, target)` from `scripts/metrics.py`.
    outcome: A dict with `rise_time`, `overshoot_percent`, `steady_state_error`, and `settling_time`.

anti_patterns:
  - Reimplementing the metric definitions inline instead of calling `scripts/metrics.py` — silent drift in thresholds (10/90, ±2%, final 10%) is the most common source of bad numbers.
  - Returning 0 when rise time or settling time is undefined. The functions return None on purpose; report it as such.
  - Computing steady-state error from the full trace rather than the final settled portion.
  - Using a different settling tolerance without saying so. Default is ±2% of target; override via the `tolerance` argument and call out the change in the report.
  - Calling `max(values)` against a target that the response approaches from above (overshoot definition assumes a rising step from below).
```
