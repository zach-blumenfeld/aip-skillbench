# Source notes — pid-controller AIP conversion

## Conversion intent

Convert the curated Anthropic-style `pid-controller` skill at
`vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/pid-controller/SKILL.md`
into AIP procedure form so an agent can implement PID feedback control for
the ACC simulation task autonomously.

The source is a freeform markdown brief covering: control law, a reference
discrete-time Python implementation, anti-windup options, and a manual
tuning order.

## Schema choice

Procedure (`procedure.schema.json`). This is a how-to: build a class, choose
an anti-windup strategy, tune three gains. Steps map cleanly onto the
procedure graph; the anti-windup choice is a `one_of`; the tuning lookup is
backed by `scripts/tuning_advisor.py`.

## Source → body mapping (completeness check)

| Source content                                | Disposition                                  |
|-----------------------------------------------|-----------------------------------------------|
| Overview paragraph                            | Mapped → `purpose`.                          |
| Control law formula                           | Mapped → `purpose` + `emit-pid-class` step.  |
| Discrete-time Python class                    | Mapped → `scripts/emit_pid_controller.py` (verbatim body in TEMPLATE). |
| Anti-windup overview (3 options)              | Mapped → `choose-anti-windup` step `one_of`, details in `references/anti-windup.md`. |
| Manual tuning order                           | Mapped → `tune-gains` step; codified in `scripts/tuning_advisor.py --procedure`. |
| Effect-of-each-gain bullets                   | Mapped → `scripts/tuning_advisor.py --effects` and `--symptom`. |

No content was dropped.

## Scripts

- `scripts/emit_pid_controller.py` — writes the canonical PID class to a
  target path. The body is identical to the code shown in the source
  SKILL.md, plus an output-clamp guard.
- `scripts/tuning_advisor.py` — lookup table mapping observed closed-loop
  symptoms (overshoot, oscillation, steady-state error, etc.) to which gain
  to adjust and in which direction; also prints the canonical manual-tuning
  procedure and the effect-of-each-gain summary.

## Frontmatter

`name` is preserved as `pid-controller` so the ACC task's mounted skill
path continues to resolve. Description retains the original keywords
("adaptive cruise control", "throttle/brake", "feedback control") so the
agent picks the skill on the same prompts.
