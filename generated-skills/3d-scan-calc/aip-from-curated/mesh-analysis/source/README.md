# Authoring notes — mesh-analysis (AIP)

Source: `ORIGINAL_SKILL.md` (a curated Agent Skill for 3D mesh / binary STL
analysis with material-ID extraction). Re-cast into AIP using the shared
`procedure.schema.json`.

## Schema choice

`procedure.schema.json` — this skill is a small execution graph:

1. parse STL + isolate largest component → `(volume, material_id)`
2. resolve material_id → density via a task-provided reference
3. align units → multiply → write report JSON

No bespoke schema needed.

## Script vs prose decisions

- `analyze-mesh` → **script** (`scripts/mesh_tool.py`). Binary STL parsing,
  vertex-quantized connected-components, and signed-tetrahedron volume are
  deterministic, mechanical, and easy to get wrong by hand. Copied verbatim
  from the source skill.
- `lookup-density` → **prose**. Resolving a material ID against a task-
  provided reference (markdown table, datasheet, etc.) hinges on interpreting
  the input the user supplies; the reference format varies per task and the
  agent must read it, not hard-code lookups.
- `align-units` → **prose**. Whether to scale depends on what units the STL
  uses (commonly mm or cm, never assumed) and what units the density table
  uses (commonly g/cm³). The agent must read the task to decide; we encode
  the conversion rule (1 cm³ = 1000 mm³) in the description.
- `compute-mass` → **prose**. One multiplication. Scripting it would add
  ceremony without value.
- `write-report` → **prose**. The output schema is task-specific (the agent
  is told the exact JSON shape in the task prompt); a generic writer would
  guess at field names.

## Source coverage

Every distinct piece of `ORIGINAL_SKILL.md` is mapped into the AIP body:

| Source content                            | AIP body location                    |
|-------------------------------------------|--------------------------------------|
| "Analyze STL / volume / components"        | `purpose`, `trigger_when`            |
| "Noise filtering — largest connected"      | `analyze-mesh.description`, `anti_patterns` |
| "Attribute extraction (material ID)"       | `analyze-mesh` outputs               |
| Basic workflow code snippet                | `analyze-mesh.description` usage note |
| Mass = Volume × Density                    | `compute-mass`                       |
| Unit warnings (mm vs cm vs in)             | `align-units`, `anti_patterns`       |
| "Binary STL handled automatically"         | `purpose`, captured by script        |
| "2-byte attribute used for color/material" | `analyze-mesh` outputs               |

No deliberate drops.

## Validation

Run from this repo root:

```
uv run .claude/skills/aip/scripts/validate.py \
  generated-skills/3d-scan-calc/aip-from-curated/mesh-analysis
```
