# Source materials — grpo (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/debug-trl-grpo/environment/skills/grpo/` into AIP
format. The original SKILL.md is preserved verbatim in `ORIGINAL_SKILL.md`, and
the schema the AIP body validates against is bundled as `procedure.schema.json`
(the canonical `procedure` schema from the AIP spec — `$id:
https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`).

The `name:` frontmatter is unchanged (`grpo`) so the mounted skill name matches
what the task expects.

## Schema choice

The original is an algorithm reference whose core content is the GRPO
*training-step pipeline*: sample -> decode -> score -> advantage -> log-probs ->
loss -> update. A pipeline is exactly the execution graph the `procedure` schema
models (`steps` with `depends_on` edges, `inputs`/`outputs`), and the schema's
optional fields (`scope_and_approval`, `search_shortcuts`, `scenarios`,
`anti_patterns`) carry the remaining reference content. So `procedure` was
adopted as-is rather than drafting a new `reference`-style schema — consistent
with every other conversion in this repo and with AIP's bias toward schema
reuse. The steps are framed as the canonical algorithm stages (each carrying its
formula, invariant, and failure mode) used as a *spec to verify an
implementation against* — the use the original `description` calls out
("verify whether a specific implementation detail matches the algorithm
specification").

Note the sibling skill `rl-post-training` in this same task compiles to the same
schema but plays a different role: it is the generic RL-debugging *procedure*
(triage table, five-stage diagnostic walk, fix-narrowly methodology). This
`grpo` skill is the GRPO *algorithm reference* (the precise per-stage math,
hyperparameter ranges, PPO/REINFORCE relationship) — the "what is correct" that
the diagnostic procedure verifies against. The two overlap in domain but are
intentionally distinct; `grpo` is self-contained and does not depend on the
sibling being mounted.

## Content mapping (completeness check)

Every distinct piece of the original SKILL.md was classified:

- **Overview + key insight** (critic-free, group-mean baseline) -> `purpose`
  (mapped).
- **Training Loop** (the 7-step pipeline) -> `steps` `sample-completions`,
  `decode-completions`, `score-completions`, `compute-advantages`,
  `compute-log-probs`, `compute-loss`, `update` — ordering expressed via
  `depends_on` (mapped). The original's step 2 "decode to text" is given its own
  step because it is where one of the canonical bugs lives.
- **Advantage Estimation** (formula, epsilon meaning, properties, the
  "signal vanishes if epsilon too large / rewards constant" failure mode) ->
  `compute-advantages` step (mapped).
- **Log-Probability Computation** (log-softmax formula, the `log_prob <= 0`
  critical invariant, sequence-level sum, selective-variant equivalence to
  `F.log_softmax`) -> `compute-log-probs` step (mapped).
- **Loss Function** (ratio, clipped surrogate, KL penalty, total) and the
  component-purpose table -> `compute-loss` step (mapped; the table's three
  rows folded inline as the role of ratio, clipping, and beta*KL).
- **Key Hyperparameters table** (num_generations, beta, clip epsilon, advantage
  epsilon, learning_rate with typical ranges and effects) -> folded into the
  owning steps: G into `sample-completions`; advantage epsilon into
  `compute-advantages`; clip epsilon, beta, and learning rate into
  `compute-loss` (mapped — each range lives where it is actionable; also echoed
  in `anti_patterns`).
- **Available References table** -> `search_shortcuts[References]` plus inline
  load guidance in the steps that need each file (`decode-completions`,
  `compute-log-probs`, and the `search_shortcuts` body) (mapped).

No source content was dropped.

## v0.2 -> v0.3a2 note

The `procedure` schema (v0.3a2) has no `decisions`, `tables`, or `reference`
field and its root is `additionalProperties: false`. The original's two lookup
tables (component-purpose, hyperparameters) were therefore re-homed into the
prose of the steps that own each row rather than kept as standalone tables. The
numbers that are *checkable on fixed inputs* (log-prob non-positivity and
F.log_softmax match, advantage epsilon magnitude, decode round-trip) are encoded
in `scripts/verify_grpo_math.py`, reached via the `verify-against-spec` step's
`script:` edge.

## Why the algorithm-spec steps stay prose (not script-backed)

AIP best practice asks that steps carrying numeric thresholds or lookup tables
be script-backed. The pipeline steps carry thresholds (`G <= 2`,
`0 < epsilon << 1`, `log_pi <= 0`, clip 0.1–0.2, LR 1e-7–5e-6) yet remain prose
because **their inputs are not available as structured data to a single
deterministic function**: these steps describe the canonical algorithm the agent
reads and reasons about against an arbitrary external implementation, not a
computation over fixed inputs. The portion that *is* input-independent and
checkable — log-prob sign/equivalence, advantage-epsilon magnitude, decode
round-trip — is encoded in `scripts/verify_grpo_math.py`, which the
`verify-against-spec` step invokes via its `script:` edge. The verifier prints
values for the agent to interpret and exits non-zero only on unambiguous
violations; it is a diagnostic the agent wires to the implementation, not a
routing function.

## Scripts and references

`references/grpo-algorithm.md` and `references/grpo-trainer-internals.md` are
copied verbatim from the source skill (byte-identical; the AIP body references
them by the same relative paths the original SKILL.md used).

One new script was authored — `scripts/verify_grpo_math.py` — that the original
skill lacked. It is the AIP value-add: the original reference explicitly advises
"verify any implementation against `F.log_softmax` on a small deterministic
input" but ships nothing runnable. The verifier makes the three checkable GRPO
invariants executable (log-prob, advantage epsilon, decode round-trip), with
adapters defaulting to TRL, mirroring the diagnostic style of the sibling
skill's `verify_pipeline.py` while staying focused on the GRPO algorithm's own
invariants.
