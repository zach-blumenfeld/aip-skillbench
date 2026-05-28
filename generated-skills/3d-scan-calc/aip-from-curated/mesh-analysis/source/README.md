# mesh-analysis — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `mesh-analysis` (the
`aip-from-curated` track for the `3d-scan-calc` task). The canonical original
is preserved verbatim at `source/ORIGINAL_SKILL.md`; the curated tool is
copied verbatim to `scripts/mesh_tool.py`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/mesh_tool.py` — verbatim copy of the curated `MeshAnalyzer` tool
  (Binary/ASCII STL parsing, signed-tetrahedron volume, connected-component
  analysis, largest-component selection, 2-byte attribute extraction).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the
  body validates against. Bundled locally so the skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a small
execution graph: parse a mesh → analyze the largest component → optionally
derive mass. That is exactly what the procedure schema models (script-backed
step nodes connected by inputs/outputs).

This skill targets **v0.3a2**. The prior committed version targeted v0.2 and
used a `decisions:` field, which v0.3a2 removed. That decision content is
re-expressed here as `scenarios` (signal → action illustrations) plus
`anti_patterns`, and conditional logic stays inside `scripts/mesh_tool.py`.

## Scope (faithful to the curated skill — not the instruction variant)

The curated skill is a **general tool wrapper**: it provides `MeshAnalyzer`
and stops at geometric properties (volume, component, material ID). Mass
derivation is left to the agent, because density comes from a task-supplied
reference whose location and format are unknown at authoring time. This
conversion preserves that scope deliberately. The sibling
`aip-from-instruction/stl-mass-from-scan` skill is the task-specific variant
that bundles a full mass/density/unit pipeline; the two tracks intentionally
differ and this one is not re-scoped to match it.

## The mass step is intentionally prose, not script

AIP best practice: a step whose description contains "if" or a numeric
calculation should be backed by a script. The `derive-mass-if-needed` step
contains both (`mass = volume * density`, "if the task requires mass"), yet
it is kept as a prose step. This is the documented exception: **its inputs
are not available as structured data at authoring time.** The density value
comes from a per-task material reference (e.g. a density table) whose
location, schema, and unit string are unknown when the skill is authored,
and the curated tool deliberately does not parse it. The actual arithmetic
is a single multiply once the units match. The real, non-obvious knowledge
(unit handling) is surfaced in `purpose`, the step description, and
`anti_patterns`, where the agent reads it before acting.

## Source-content classification (completeness check)

- "When to Use" (geometric analysis / noise filtering / attribute
  extraction) → **Mapped** to `purpose` + `trigger_when`.
- Basic workflow (sys.path import → `MeshAnalyzer(path)` →
  `analyze_largest_component()` → read `main_part_volume`,
  `main_part_material_id`) → **Mapped** to steps `load-mesh` and
  `analyze-largest-component` (both backed by `scripts/mesh_tool.py`).
- "Calculating Mass" (read material ID → density lookup → `Mass = Volume *
  Density`) → **Mapped** to step `derive-mass-if-needed` (prose; see above).
- "Critical Note on Units" (volume is in STL coordinate units cubed; do not
  assume mm/in; multiply directly when density unit matches) → **Mapped** to
  the `derive-mass-if-needed` description, a units `scenario`, and
  `anti_patterns`.
- "Critical Notes" — Binary support + ASCII fallback losing material IDs;
  2-byte attribute extraction → **Mapped** to `load-mesh` description, an
  ASCII-fallback `scenario`, and an `anti_pattern`.
- Hard-coded example path `/root/.claude/skills/mesh-analysis/scripts` →
  **Deliberate drop** of the literal path. Generalized to "add the skill's
  `scripts/` directory to `sys.path`" so the skill is portable; the absolute
  mount path is environment-specific.
