# Source & authoring notes — trl-grpo-debugging

## Intent

Authored from the task instruction alone (`source/instruction.md`), with no inspection of any
pre-existing skill. The instruction is terse:

> Training a countdown math task using TRL with GRPO; the new model shows no improvement.
> Source code is at `/app/trl`. Find and fix the bug(s). DO NOT modify the training script
> (`/app/train_grpo.py`) or reward function (`/app/reward_fn.py`).

This implies a precise task *type*: a small bug has been planted in the TRL GRPO trainer that
breaks learning silently (flat reward), and the fix must live in the library source only. The
skill therefore encodes the specialized knowledge an agent needs to solve any instance of this
type autonomously — not the answer to one instance.

## Schema choice

`procedure.schema.json` (reused, bundled in this folder). The work is a diagnostic
workflow / runbook: a graph of script-backed steps with inputs/outputs, plus trigger
conditions, scope/approval gates, modes, worked scenarios, and anti-patterns. No new schema
was needed.

## Domain knowledge captured (and where)

- **Correct GRPO algorithm + invariants** → `references/grpo-algorithm.md`. The six computation
  sites (advantage, per-token logp/shift, ratio, clipped loss sign, completion mask, KL) with
  correct code forms, so the agent can diff the trl source against them.
- **No-improvement failure modes** → `references/grpo-bug-catalog.md`. Categories A–H, each with
  symptom, site, static + runtime detection, and buggy→correct form. Triage order keyed to the
  reward-curve trend.
- **Fast localization** → `scripts/locate_trl_changes.py`. Surfaces a version-control diff (the
  usual plant) and greps the key sites — automates the "where to look" lookup logic.
- **Deterministic diagnosis + verification** → `scripts/grpo_invariants.py`. Holds the numeric
  thresholds and the invariant→bug-category lookup (scriptable logic per AIP best practice), and
  the reward-improving gate for the verify step.

## Scriptable-logic decisions

- Threshold rules and the invariant→category mapping are numeric/lookup logic → `grpo_invariants.py`,
  not prose.
- Site-grep patterns and git-diff triage are a fixed lookup/automation → `locate_trl_changes.py`.
- The metrics are *live training tensors*, not data available to a standalone script, so the
  capture step (`instrument-and-capture`) stays a prose step: the agent writes a small
  instrumentation patch (variable names vary by TRL version) and dumps summary stats to JSON,
  which the script then validates. This is the documented exception to "scriptable logic must be
  a script" — the inputs aren't structured until the agent produces them.

## Instruction-coverage classification

| Instruction content | Status | Where |
|---|---|---|
| Training a countdown-math task with TRL + GRPO | Mapped | trigger_when, purpose, scenario 1 |
| "no improvement" symptom | Mapped | purpose, confirm-symptom-and-scope, bug catalog (flat-curve focus) |
| Source code at `/app/trl` | Mapped | locate-trl-and-changes (default --trl-path /app/trl) |
| "Check if there is any bug and fix them" | Mapped | full diagnose→fix→verify loop |
| DO NOT modify train_grpo.py / reward_fn.py | Mapped | do_not_use_when, scope_and_approval, locate script off-limits reminder, anti_patterns |

No deliberate drops. Specific paths (`/app/...`, the exact countdown task) are treated as
instance details; the skill generalizes to the task type while defaulting to those paths.
