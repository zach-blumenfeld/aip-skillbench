# Source materials — rl-post-training (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/debug-trl-grpo/environment/skills/rl-post-training/`
into AIP format. The original SKILL.md is preserved verbatim in
`ORIGINAL_SKILL.md`, and the schema the AIP body validates against is bundled
as `procedure.schema.json` (the canonical `procedure` schema from the AIP
spec — `$id: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`).

## Schema choice

The original is a diagnostic procedure: a five-stage pipeline walk with
mathematical invariants, an observation→culprit triage table, and explicit
anti-patterns. The bundled `procedure` schema (v0.3a2) captures this shape
(`steps`, `scope_and_approval`, `scenarios`, `anti_patterns`), so it was
adopted as-is rather than drafting a new schema.

## v0.2 → v0.3a2 note

A prior compilation of this skill targeted AIP v0.2 and used a `decisions:`
field (signal → action pairs) to carry the Key Mathematical Invariants table.
The v0.3a2 `procedure` schema has no `decisions` field (root is
`additionalProperties: false`), so that content was re-homed:

- The **invariant + check-method** for each invariant moved into the stage
  step that owns it (`log_prob <= 0`, match `F.log_softmax`, softmax sums to 1
  → `verify-log-prob-computation`; `0 < epsilon << 1`, advantages non-zero,
  mean-centered groups → `verify-advantage-computation`; decoding preserves
  content → `verify-generation-and-decoding`).
- The **triage routing** (loss flat → Stages 1–3, model degenerates → Stage 4,
  etc.) became a dedicated front `triage` step, mirroring the Triage table in
  `references/diagnostic-workflow.md`.
- The numeric **assertions** themselves are encoded in
  `scripts/verify_pipeline.py`, reached via the `run-verifier` step's
  `script:` edge.

## Content mapping (completeness check)

Every distinct piece of source content was classified:

- **Core Concepts** (pipeline diagram + framing) → `purpose` (mapped).
- **Diagnostic Methodology preamble** (work stages in order; each stage
  depends on the previous) → `purpose` + `scope_and_approval` + step
  `depends_on` chains (mapped).
- **Stages 1–5 of the diagnostic methodology** → `steps`
  `verify-reward-signal`, `verify-advantage-computation`,
  `verify-log-prob-computation`, `verify-loss-computation`,
  `verify-generation-and-decoding` (mapped; stage-ordering constraint
  expressed via `depends_on`).
- **Fixing, Not Rewriting** → step `fix-narrowly` + several `anti_patterns`
  (mapped).
- **Key Mathematical Invariants table** → invariant + check-method folded into
  the owning stage steps; numeric assertions encoded in
  `scripts/verify_pipeline.py` reached via `run-verifier` (mapped — see
  "v0.2 → v0.3a2 note").
- **Common Pitfall Categories (7-item list)** → embedded inline in step
  `match-against-pitfall-catalog`, which also names the deeper reference doc
  (mapped). Four representative pitfalls are additionally worked as
  `scenarios` (epsilon dominates, reference-model not frozen, decoding blanks
  a completion shape, SFT-scale LR) — drawn verbatim from
  `references/common-pitfalls.md`.
- **Available References table** → `search_shortcuts[References and verifier]`
  plus inline load instructions in the steps that need each resource
  (`match-against-pitfall-catalog`, `verify-generation-and-decoding`,
  `run-verifier`) (mapped — load guidance lives where it is actionable).
- **Triage table** (`references/diagnostic-workflow.md`) → surfaced as the
  `triage` step (mapped; previously only referenced).

No source content was dropped.

## Why the diagnostic stages stay prose (not script-backed)

AIP best practice requires that steps containing numeric thresholds or lookup
tables be script-backed. The five stage steps and the triage step carry
thresholds (`G ≤ 2`, `0 < epsilon < 1`, `log_prob <= 0`) and an
observation→culprit table, yet remain prose because **their inputs are not
available as structured data to a single deterministic function**: the agent
is reasoning about an arbitrary external training pipeline, observed metrics,
and qualitative symptoms. The portion that *can* be automated — the numeric
invariant assertions — is encoded in `scripts/verify_pipeline.py`, which the
`run-verifier` step invokes via its `script:` edge. The verifier itself
requires the agent to wire three project adapters, so it is a manual
diagnostic, not a routing function. This matches the original skill's design,
where the script "does NOT tell you whether the pipeline is correct" but
prints values for the agent to interpret.

## Scripts and references

No new scripts authored. `scripts/verify_pipeline.py`,
`references/common-pitfalls.md`, and `references/diagnostic-workflow.md` are
copied verbatim from the source skill; the AIP body references them by the
same relative paths the original SKILL.md used. The `name:` frontmatter is
unchanged (`rl-post-training`) so the mounted skill matches what the task
expects.
