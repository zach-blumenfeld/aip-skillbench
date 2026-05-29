---
name: simulation-metrics
description: Use this skill when calculating control system performance metrics such as rise time, overshoot percentage, steady-state error, or settling time for evaluating simulation results.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute standard time-domain step-response metrics — rise time,
  overshoot percent, steady-state error, settling time — from a
  simulation time-series, and judge whether each metric meets its
  requirement target. Used to score setpoint-tracking controllers such
  as PID-tuned cruise control, ACC speed/distance loops, or any system
  whose output should converge on a fixed target.

trigger_when:
  - Evaluating simulation output against requirements like "rise time <10s, overshoot <5%, steady-state error <0.5".
  - PID-tuning loops that need objective per-candidate metrics.
  - Reporting ACC, cruise-control, or other setpoint-tracking performance.
  - Producing a metrics table for a report (e.g., acc_report.md).

do_not_use_when:
  - The system is not setpoint-tracking (e.g., pure path-following with no constant target).
  - Frequency-domain metrics (gain/phase margin, bandwidth) are required — this skill covers time-domain step response only.

steps:
  - name: load-trace
    description: >
      Read the simulation results (CSV with a time column and the
      tracked variable column, e.g., `time` + `ego_speed`, or `time` +
      `distance`). Drop rows where either value is missing or non-numeric;
      keep rows in time order.
    outputs:
      - name: times
        type: list[float]
      - name: values
        type: list[float]
      - name: target
        type: float
        description: Setpoint from the task spec (e.g., 30.0 m/s for ACC cruise speed).

  - name: compute-metrics
    description: >
      Run scripts/metrics.py to compute rise time, overshoot percent,
      steady-state error, and settling time for the tracked variable
      against its target. Importable as a module
      (`from metrics import rise_time, overshoot_percent, steady_state_error, settling_time`)
      or callable as a CLI
      (`python scripts/metrics.py --csv <path> --column <col> --target <val>`).
      Any metric that is undefined for the trace (target never reached,
      band never held) returns null/None.
    script: scripts/metrics.py
    inputs:
      - name: times
        type: list[float]
      - name: values
        type: list[float]
      - name: target
        type: float
      - name: tolerance
        type: float
        nullable: true
        description: Settling-time band as a fraction of target. Default 0.02 (±2%).
      - name: final_fraction
        type: float
        nullable: true
        description: Tail portion of trace averaged for steady-state error. Default 0.1.
    outputs:
      - name: metrics
        type: object
        description: '{rise_time, overshoot_percent, steady_state_error, settling_time}; values may be null.'

  - name: compare-to-targets
    description: >
      For each metric in the task's requirement list, emit a pass/fail
      verdict against the threshold (e.g., rise_time < 10, overshoot_percent
      < 5, steady_state_error < 0.5). A null metric is a fail, not a pass —
      report it as "undefined / target not reached" rather than silently
      skipping it.
    inputs:
      - name: metrics
        type: object
      - name: targets
        type: object
        description: Per-metric pass thresholds drawn from the task spec.
    outputs:
      - name: verdict
        type: object

  - name: report
    description: >
      Render the metrics table and per-target verdict. When the task asks
      for an acc_report.md, include the metric values verbatim and call
      out each failing requirement. Recommend concrete next action when a
      requirement fails (e.g., reduce overshoot → lower kp or raise kd).
    inputs:
      - name: verdict
        type: object
    outputs:
      - name: report
        type: string

scenarios:
  - need: PID-tuned ACC simulation produces simulation_results.csv with ego_speed converging on 30 m/s; verify against {rise_time <10, overshoot <5%, steady_state_error <0.5}.
    action: >
      `python scripts/metrics.py --csv simulation_results.csv --column ego_speed --target 30.0`,
      then compare each returned metric to its threshold.
    outcome: Per-target pass/fail printed; failing metrics trigger retuning.

  - need: Verify ACC following-distance loop holds within 2m of the safe-gap setpoint.
    action: >
      `python scripts/metrics.py --csv simulation_results.csv --column distance --target <safe_gap>`;
      use the `steady_state_error` field for the verdict against `<2`.
    outcome: Distance-loop steady-state error reported; failure points at distance-PID retuning.

anti_patterns:
  - Computing overshoot before the system has reached the target — `max(values) <= target` returns 0% spuriously when the trace is still rising.
  - Using the full trace for steady-state error — transient values dominate the average. The script's `final_fraction` (default 0.1) exists precisely to window the tail.
  - Treating settling time as "first time inside the band" — the band must be held to the end of the trace; a re-exit resets the candidate. Don't reimplement this as a one-shot threshold check.
  - Reporting a null metric as "ok" — null means the metric is undefined (target never reached, band never held). Surface it as a failure, not a pass.
  - Computing rise time as 0%-to-100% instead of 10%-to-90% — ringing makes 100% never-reached and slow tails distort 0%; the 10/90 convention is what the targets are written against.
```
