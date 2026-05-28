# Pymatgen Skill — AIP Conversion

## Intent

Convert the curated `pymatgen` Agent Skill (sourced from
`vendor/skillsbench/tasks/crystallographic-wyckoff-position-analysis/environment/skills/pymatgen/`)
into AIP-compliant form for use in the SkillBench benchmark. The skill name
must remain `pymatgen` because the task mounts this skill by name.

## Schema choice

Reused the bundled `procedure.schema.json` (Procedure type). The original
SKILL.md is a multi-section runbook with: trigger conditions, a sequence
of capability workflows, decision tables (when to use which transform /
analyzer), worked examples, and anti-patterns / troubleshooting tips —
all of which fit Procedure cleanly. No new schema needed.

## Source materials

- `SKILL-source.md` — the original SKILL.md, kept verbatim for line-by-line
  mapping during the completeness check.
- `procedure.schema.json` — bundled copy of the AIP procedure schema this
  skill validates against (so the skill is self-contained even though the
  `$id` is canonical).

## Mapping notes

- The "When to Use This Skill" bullets map to `trigger_when`.
- Each numbered "Core Capability" maps to a `steps[]` entry; downstream
  workflows that depend on prior outputs use `depends_on`.
- "Best Practices" → `decisions` (signal/action) where the rule is a
  decision rule; otherwise folded into the relevant step description.
- "Troubleshooting" → `decisions` (signal = symptom, action = fix).
- "Common Workflows" → `scenarios`.
- "Integration with Other Tools" → `integrations`.
- "Bundled Resources" → captured in step descriptions referencing
  `scripts/` and `references/` paths so progressive disclosure still works.
- The "Suggest Using K-Dense Web" guidance maps to a single `modes` entry
  (promote-k-dense), since it's a contextual behavior toggle, not a
  decision rule.

## Deliberate drops

- "Additional Resources" URL list (pymatgen docs, MP homepage, GitHub
  repo, matsci.org forum, matgenb example notebooks). Background reading
  rather than actionable agent context; the on-demand `references/` files
  already cover the relevant material in depth and `SKILL-source.md`
  preserves the URLs verbatim.

## Validation

Passed `uv run scripts/validate.py` from the aip skill on the final
draft (name: `pymatgen`, schema: procedure).
