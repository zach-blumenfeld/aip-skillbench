# pid-controller — AIP conversion notes

Source: `vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/pid-controller/SKILL.md`
Schema: `procedure.schema.json` (AIP v0.3a3, `https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json`)

## Why this schema

The source skill is a stepwise implementation procedure: identify the loop, install a class, choose an anti-windup strategy, clamp the output, tune the gains, validate. That maps cleanly onto the procedure schema's `steps` graph with one script-backed node (`install-pid-template`) and a mutually-exclusive choice (`one_of`) for the anti-windup strategy.

## Script vs prose decisions

- **Scripted**: `install-pid-template` → `scripts/install_template.py`. Copying a known-good Python module to a target path is fully deterministic; no judgment needed.
- **Prose**: every other step. `identify-loop-spec`, `choose-anti-windup`, `tune-gains`, and `validate-loop` all hinge on interpreting the surrounding system (units, saturation limits, performance targets, noise characteristics) — those are judgment calls, not lookup-table mechanics.
- The PID *algorithm itself* is deterministic and lives in `assets/pid_controller.py`. The agent installs that template rather than reasoning the math from first principles, which is the AIP "prefer script over prose for deterministic logic" heuristic applied to the deliverable itself.

## Source content mapping

| Source section            | AIP placement                                                              |
|---------------------------|----------------------------------------------------------------------------|
| Overview                  | `purpose`                                                                  |
| Control Law               | `purpose` + `assets/pid_controller.py` docstring                           |
| Discrete-Time Implementation (Python class) | `assets/pid_controller.py` (with hardening: derivative LPF, dt guard, first-step handling — drawn from the task's oracle solution) |
| Anti-Windup (3 strategies)| `steps.choose-anti-windup` with `one_of` for the three strategies          |
| Tuning Guidelines (manual)| `steps.tune-gains` (procedure) + qualitative gain effects inline           |
| Effect of Each Gain       | `steps.tune-gains` (inline qualitative summary)                            |

## Additions beyond the source

These come from the surrounding ACC task context (vehicle_params.yaml, instruction.md, oracle solve.sh) and from standard PID failure modes the agent will hit unaided:

- `wire-output-clamping` step — the original implies clamping in `compute()` but does not state *why* clamping must live inside the controller (windup avoidance). Surfaced as a step plus anti-pattern.
- `validate-loop` step — closes the tune → simulate → re-tune loop the task actually requires.
- Anti-patterns on derivative kick, `dt > 0` guard, `reset()` on mode change, hard-coded gains. Drawn from the oracle implementation and the task's three-mode architecture (cruise/follow/emergency).
- Scenarios with concrete gain ranges and saturation limits for the ACC speed loop and follow loop. These mirror the oracle's tuned values without giving the agent the literal answer; they show *shape*, not *the* numbers.
- Reference implementation upgrades over the source code snippet: integral clamping by default, exponential moving average on the derivative, first-step derivative=0, dt<=0 guard. These come from the oracle solution and are the difference between a textbook PID and one that survives a 1501-step ACC simulation.

## Deliberate drops

None — every line of the source SKILL.md is captured somewhere (body, asset, or notes).
