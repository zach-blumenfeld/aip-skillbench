# mesh-analysis — AIP conversion notes

## Source

- `original-SKILL.md` — the curated Agent Skill from `vendor/skillsbench/tasks/3d-scan-calc/environment/skills/mesh-analysis/SKILL.md`.
- The original ships one Python module, `scripts/mesh_tool.py`, exposing `MeshAnalyzer` with three public methods: `get_volume`, `get_components`, `analyze_largest_component`. It auto-detects Binary STL vs ASCII STL and surfaces the 2-byte per-triangle attribute (commonly material ID) on binary parse.

## Schema choice

Reused `procedure.schema.json` from the bundled AIP schemas. The work the skill encapsulates is a short execution graph (parse → isolate main part → derive mass), which is exactly what a procedure models. No domain-specific schema warranted.

## Body structure

Three steps wire the graph end-to-end:

1. `extract-volume-and-material` — script-backed by `scripts/mesh_tool.py`. The script's `analyze_largest_component()` method is the source of truth for the parsing, component-isolation, and volume-integration logic. The step description is one line.
2. `lookup-density` — prose step. The mapping from `material_id` to density is supplied by the task (typically a small reference table). No script: the lookup table is task-scoped, not skill-scoped.
3. `compute-mass` — prose step. The arithmetic is a single multiplication; the judgment is in unit alignment (volume coordinate units cubed must match the volume part of the density unit). This requires reasoning about task-supplied unit strings, so it stays prose.

## Source content mapping

| Source content | Disposition |
|---|---|
| "Use this skill for: Geometric Analysis, Noise Filtering, Attribute Extraction" | Mapped → `purpose` + `trigger_when` |
| "The tool is provided as a Python module in the `scripts/` directory" | Mapped → `extract-volume-and-material` step (script path) |
| Basic Workflow Python snippet (sys.path append + import) | Mapped → `scenarios[0]` (worked example showing the invocation form the original docs taught) |
| Calculating Mass: read material_id, look up density, multiply | Mapped → `lookup-density` + `compute-mass` steps |
| Critical Note on Units (don't assume mm/inches, check task units) | Mapped → `compute-mass` step body and `anti_patterns` |
| Binary Support note | Mapped → `purpose` (binary-first, ASCII fallback noted) and an anti-pattern about ASCII losing material IDs |
| Attribute extraction note | Mapped → `purpose` and `extract-volume-and-material` outputs |

No source content deliberately dropped.

## Script preservation

`scripts/mesh_tool.py` is copied verbatim from the source, including its `__main__` block that prints `analyze_largest_component()` as a Python dict. Agents may either import the module or invoke it as a CLI; both forms appear in `scenarios`.
