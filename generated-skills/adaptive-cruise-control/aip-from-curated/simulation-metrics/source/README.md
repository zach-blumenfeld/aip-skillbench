# simulation-metrics — AIP port notes

## Source

- `original-SKILL.md` — the curated Agent Skill bundled with the
  `adaptive-cruise-control` SkillsBench task. Defines four control-system
  step-response metrics as Python snippets: rise time, overshoot percent,
  steady-state error, settling time.
- `task-instruction.md` — the task prompt, included for context on which
  targets the agent must verify (speed rise time <10s, overshoot <5%,
  steady-state error <0.5 m/s, distance steady-state error <2m, etc.).
- `procedure.schema.json` — bundled copy of the AIP `procedure` schema
  v0.3a3.

## Schema choice

The four metric routines form a small linear procedure (load trace →
compute metrics → compare to targets → report). The `procedure` schema
captures that execution graph directly; no new schema is needed.

## Script vs. prose split

| Step | Backing | Why |
|---|---|---|
| load-simulation-results | prose | Trivial CSV read; the value column varies (ego_speed, distance, …) and the agent already knows how. |
| compute-metrics | `scripts/metrics.py` | Deterministic math with off-by-one risks (10/90% thresholds, ±tolerance band re-entry semantics, tail-mean window). Must be exact across runs. |
| compare-to-targets | prose | Targets come from the task spec at runtime; a simple `<`/`>` comparison per metric is well within agent reasoning, and the set of targets differs from task to task. |
| report | prose | Pure presentation; varies by request (acc_report.md vs inline summary). |

## Algorithm preservation

`scripts/metrics.py` carries the four functions byte-equivalent in
behavior to the originals:

- `rise_time` — first time `v >= 0.1 * target`, first time `v >= 0.9 * target`, return difference. `None` if either threshold is never hit.
- `overshoot_percent` — `0.0` when `max(values) <= target`, else `(max - target)/target * 100`.
- `steady_state_error` — `|target - mean(values[-final_fraction:])|`.
- `settling_time` — first time entering the ±tolerance band and staying there to the end; a single re-exit resets the candidate.

A `compute_all` helper and a CLI wrapper are added on top so the script
is callable both as an importable module and as a one-shot tool.

## Deliberate drops

None. Every metric in the source SKILL.md is mapped to a function in
`scripts/metrics.py`. The "Usage" snippet at the end of the source file
is encoded as a scenario in the AIP body rather than verbatim prose,
since its content (print four metrics for a target of 30.0) is exactly
what the `compute-metrics` step does.
