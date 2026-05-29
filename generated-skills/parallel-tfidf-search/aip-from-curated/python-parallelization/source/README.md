# Source / Rationale — python-parallelization (AIP from curated)

This folder bundles the inputs used to produce the AIP version of the
`python-parallelization` skill and records the authoring decisions made
during the transition.

## Files

- `SKILL.md` — the original curated Agent Skill, copied verbatim from
  `vendor/skillsbench/tasks/parallel-tfidf-search/environment/skills/python-parallelization/SKILL.md`.
  Source of truth for the workflow steps, patterns, decision tree, safety
  requirements, common pitfalls, and verification checklist.
- `procedure.schema.json` — the AIP procedure schema bundled locally so the
  skill is self-contained. The body of `../SKILL.md` validates against this.

## Schema choice

Used the AIP `procedure` schema (`procedure.schema.json`) without
modification. The original SKILL.md is shaped exactly like a procedure —
analyze → classify → select strategy → transform → verify — with mutually
exclusive sub-step alternatives (workload class, transformation pattern)
that map cleanly to `one_of`. No new schema was required.

## Script vs prose decisions

| Original section | AIP location | Why |
|------------------|--------------|-----|
| Workflow (5 steps) | `steps[]` in body | Direct mapping. |
| Parallelization Decision Tree | `references/decision-tree.md` (loaded on demand by `classify-workload`) | Tree contains code-fenced ASCII that does not embed cleanly inside a YAML body; agents only need it once classification is in question. |
| Transformation Patterns 1–4 | `references/transformation-patterns.md` | Heavy code blocks; progressive disclosure keeps the body lean. |
| (New) Pattern 5 — Pool initializer | `references/transformation-patterns.md` | Added because the TF-IDF batch-search target (2×) is not reachable without preloading the index once per worker. The original SKILL.md hinted at it ("Memory explosion … use shared memory for large data") but did not show the canonical Pool-initializer code. |
| (New) Pattern 6 — MapReduce over batches | `references/transformation-patterns.md` | Added to capture the per-batch tokenize → reduce DF → per-shard inverted-index build flow that the curated benchmark expects. The original SKILL.md covered only the per-item Pool.map pattern. |
| Parallelization Candidates table | `references/decision-tree.md` | Lookup table; lives next to the decision tree it serves. |
| Safety Requirements | `references/safety-and-pitfalls.md` + `scope_and_approval` (worker-level rules) + `anti_patterns` (per-rule prohibitions) | Split between procedural body (concise) and the loadable reference (full prose). |
| Common Pitfalls | `references/safety-and-pitfalls.md` + `anti_patterns` | Same split. The anti-patterns block in the body is the high-signal subset; the reference is the long form. |
| Verification Checklist | `scripts/verify_parallel.py` + `references/safety-and-pitfalls.md` | The checklist's checks (output match within tolerance, speedup target, bounded workers, etc.) are deterministic — scripted. The reference keeps the human-readable form for context. |

## Why a script for `verify`

The original SKILL.md ends with a bulleted verification checklist. Every
item on it is mechanical: import both modules, build both indexes, compare
IDF dicts within tolerance, run a batch of queries through both pipelines,
compare top-k by (doc_id, score), measure wall-clock for each phase, and
check ratios against thresholds. Encoding this as a script
(`scripts/verify_parallel.py`) means:

- the agent gets a single command instead of a multi-step checklist,
- the thresholds (1.5×, 2×, 1e-6) live in one place and can be overridden
  via flags when a task specifies different ones,
- failure surfaces as JSON-Lines diagnostics on stderr that the agent can
  read and act on without re-deriving what to compare.

## Deliberate drops

Nothing material from the source SKILL.md was dropped. The Markdown
formatting of the original (headings, tables, fenced before/after blocks)
does not translate into the YAML body directly — that content was relocated
to `references/` rather than dropped. The original's `## Common Pitfalls`
list is preserved in two places: condensed bullets in `anti_patterns`
(always-loaded body) and full prose in `references/safety-and-pitfalls.md`
(loaded on demand). This is duplication, but it is intentional —
anti-patterns are high-signal enough to keep in the body budget.

## Skill name

`name: python-parallelization` is unchanged. The curated benchmark mounts
the skill folder by that exact name; renaming would break the test
harness.
