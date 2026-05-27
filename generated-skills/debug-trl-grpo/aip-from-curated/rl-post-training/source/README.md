# Source materials — rl-post-training (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/debug-trl-grpo/environment/skills/rl-post-training/`
into AIP format. The original SKILL.md is preserved verbatim in
`ORIGINAL_SKILL.md`, and the schema the AIP body validates against is bundled
as `procedure.schema.json` (the canonical `procedure` schema from the AIP
spec — `$id: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json`).

## Schema choice

The original is a diagnostic procedure: a five-stage pipeline walk with
mathematical invariants, signal → action mappings, and explicit
anti-patterns. The bundled `procedure` schema captures exactly this shape
(`steps`, `decisions`, `anti_patterns`, `scope_and_approval`), so it was
adopted as-is rather than drafting a new schema.

## Content mapping (completeness check)

Every distinct piece of source content was classified:

- **Core Concepts** (pipeline diagram + framing) → `purpose` (mapped).
- **Diagnostic Methodology preamble** (work stages in order; each stage
  depends on the previous) → `purpose` + `scope_and_approval` + step
  `depends_on` chains (mapped).
- **Stages 1–5 of the diagnostic methodology** → `steps`
  `verify-reward-signal`, `verify-advantage-computation`,
  `verify-log-prob-computation`, `verify-loss-computation`,
  `verify-generation-and-decoding` (mapped, with the stage-ordering
  constraint expressed via `depends_on`).
- **Fixing, Not Rewriting** → step `fix-narrowly` + several
  `anti_patterns` (mapped).
- **Key Mathematical Invariants table** → `decisions` (each invariant
  violation expressed as a signal → action pair) (mapped).
- **Common Pitfall Categories (7-item list)** → embedded inline in step
  `match-against-pitfall-catalog`, which also names the deeper reference
  doc (mapped).
- **Available References table** → load instructions embedded in the
  steps that need them (`match-against-pitfall-catalog` and `run-verifier`)
  (mapped — load guidance lives where it's actionable).

No source content was dropped.
