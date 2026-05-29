# Source Notes — logistics-rules-to-optimization

This folder bundles the canonical source materials used to compile the AIP
skill at the parent directory.

## Files

- `procedure.schema.json` — the AIP schema this skill validates against.
  Bundled locally so the skill is self-contained; identical to the
  canonical `procedure.schema.json` at the `$id` URL.
- `SKILL.md` — the original freeform-markdown skill from
  `vendor/skillsbench/tasks/bike-rebalance/environment/skills/logistics-rules-to-optimization/SKILL.md`.

## Compile Notes

- The original is a hybrid workflow + pattern reference: a 5-step
  translation procedure followed by ~200 lines of variable patterns,
  constraint code snippets, a lookup table, the pickup/dropoff
  convention, and objective assembly.
- The 5-step workflow maps directly onto the procedure schema's `steps`.
- The pattern reference material is pushed into `references/` files
  (`variable-patterns.md`, `rule-pattern-table.md`,
  `constraint-examples.md`, `inventory-pickup-dropoff.md`,
  `objective-assembly.md`) and loaded on demand from the relevant step
  — this keeps the body lean while preserving every code snippet from
  the source verbatim.
- Inline warnings in the source (no Python `abs()` on solver
  expressions, use the tightest possible `M`, don't add global
  single-visit when split service is needed) are lifted into the
  schema's `anti_patterns` field.
- One scenario covers the bike-rebalance use case the parent
  skillsbench task targets; two additional scenarios show vehicle
  routing with time windows and soft demand with absolute deviation.

## Deliberate Drops

None. Every variable pattern, constraint snippet, lookup-table row,
warning, and code example from the source `SKILL.md` is preserved either
in the body or in `references/`.

## No Scripts

The skill is fundamentally a translation reference the agent applies
semantically to a free-text problem statement. The rule → pattern
mapping is intrinsically reasoning-based, not table-lookup; encoding it
as a script would over-restrict the agent without adding determinism.
The independent validation step likewise depends on the agent's own
variable naming and model shape, so a generic validator script would be
too brittle to be useful.
