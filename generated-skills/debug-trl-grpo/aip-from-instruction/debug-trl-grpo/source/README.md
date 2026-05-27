# Source notes — `debug-trl-grpo`

This skill was authored from the task instruction at
`vendor/skillsbench/tasks/debug-trl-grpo/instruction.md` (a single
paragraph describing a stalled TRL GRPO countdown-math training run,
with the training script and reward function declared off-limits).

## What the instruction provided

- Symptom: "new model shows no improvement" on a countdown math task.
- Stack: TRL GRPO trainer.
- Source location: `/app/trl` (vendored TRL checkout).
- Constraint: do not modify `/app/train_grpo.py` or `/app/reward_fn.py`.

## What this skill adds beyond the instruction

The instruction is silent on *how* to debug; this skill encodes the
procedural knowledge a downstream agent needs:

- **GRPO algorithm reference** (`references/grpo-architecture.md`)
  derived from the DeepSeek paper and TRL upstream — derivation of the
  group-relative advantage, the loss form with KL, and the per-method
  invariants (`reward_std > 0`, `(B, L-1)` logprob shape, mask
  alignment, `loss.grad_fn` non-None).
- **Known bug-site checklist** (`references/known-bug-sites.md`) — eight
  ranked regression patterns with the broken code, the correct code,
  and the smallest fix. Drawn from the algorithm invariants, not from
  any single observed bug in /app/trl, so the agent can match by
  behaviour rather than by a specific diff.
- **Smoke-train script** (`scripts/smoke_train.sh`) — runs the
  unmodified training script for N steps and surfaces the four metrics
  that diagnose all known failure modes (`reward`, `reward_std`,
  `loss`, `kl`).
- **Static scanner** (`scripts/inspect_grpo.py`) — pattern-matches the
  trainer source against the high-priority bug patterns and verifies
  the editable install resolves to `/app/trl`.
- **Decision table** in `SKILL.md` that maps observable smoke-test
  signals to the matching bug site, so the agent doesn't have to walk
  the entire checklist when the symptom is distinctive.

## Schema choice

`procedure.schema.json` (bundled in this `source/`). The skill is a
multi-step diagnostic procedure with branching decisions, modes
(quick-triage / full-audit / revert-and-verify), worked scenarios, and
anti-patterns — a clean fit for the procedure schema. No new schema was
drafted.

## Deliberate drops

None. The instruction is so terse that nothing was discarded; everything
in the instruction is either captured directly (off-limits files,
source location, symptom) or expanded into procedural guidance.
