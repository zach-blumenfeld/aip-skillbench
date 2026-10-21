# Source material for `stl-part-mass`

## Provenance

| File | Origin | Notes |
| --- | --- | --- |
| `mesh-analysis/SKILL.md` | curated Agent Skill `mesh-analysis` | verbatim copy |
| `mesh-analysis/scripts/mesh_tool.py` | same skill, `scripts/mesh_tool.py` | verbatim copy (`MeshAnalyzer`) |
| `task-instruction.md` | the task statement the downstream agent receives | verbatim; shows the target task (binary STL with Material ID in the attribute bytes, largest component, density table lookup, `/root/mass_report.json`) |

The compiled skill's `scripts/mesh_tool.py` is adapted from the original `MeshAnalyzer`.

## Intent

Compile the single-skill `mesh-analysis` workflow (parse STL, keep the largest
connected component, read its Material ID, look up density, Mass = Volume * Density)
into an AIP procedure that runs end to end on the task container (Ubuntu 24.04, `python3`
+ pip, no numpy), so the whole thing runs on the standard library.

## Component-kind choices

| Step | Kind | Why |
| --- | --- | --- |
| `analyze-scan` | execution | Parsing, connected components, volume, and the density lookup are deterministic code. The source said "consult your density table" in prose; a table lookup is scriptable, so the script parses the markdown table and fails loudly if the ID is missing instead of leaving it to the agent. |
| `settle-units` | decision (choice) | The source's critical units note ("do not assume mm or inches; check the task instructions; same units means multiply directly") is a judgment over free text with a fixed answer space. Its answer feeds a script, so it is a decision. Threshold 0.3: picking a conversion wrongly makes the mass off by 10³ or more, so a close call gets a second look. |
| `compute-mass` | execution | Mass, unit conversion factors, and writing the exact JSON format are arithmetic and formatting. |

**No router.** Every unit answer leads to the same arithmetic with a different factor, so
the answer goes into `compute-mass` as an input. Branching would need either duplicate
producers of `main_part_mass` (which the format forbids) or steps that do nothing. A
missing Material ID ends the run with a non-zero exit and a message listing the table's
IDs; the runtime then stops and reports it, which is the right behaviour (never guess a
density).

## Changes vs the original tool (adaptations, not drops)

- **Binary detection** still uses the size check (`84 + 50*count == file size`), as the original does. Added: trailing bytes beyond the declared count are tolerated with a warning, and ASCII fallback is recorded in `mesh_report.warnings` rather than printed to stdout (stdout must be one JSON object).
- **Components**: same shared-vertex rule with coordinates rounded to 5 decimals; implemented as union-find instead of BFS over per-vertex lists, O(n) for larger scans. Same grouping.
- **Largest component** is still chosen by volume. Added warnings when the component with the most triangles is a different one, and when the main part has open edges (volume unreliable).
- **Material ID**: the original took the first triangle's attribute. Now the majority ID over the component, with a warning if IDs are mixed. Same result when the component is uniform, as it is in the task file.
- **Volume** is the same formula: absolute value of the sum of signed tetrahedron volumes / 6.

## Completeness check (source line → where it lives)

| Source content | Location in compiled skill |
| --- | --- |
| Description: volume, components, attribute data, noisy scans, debris | frontmatter `description`, `purpose`, `trigger_when` |
| When to use 1–3 (geometric analysis, noise filtering, attribute extraction) | `trigger_when` items |
| Usage: `MeshAnalyzer`, `analyze_largest_component()`, `main_part_volume`, `main_part_material_id` | `scripts/mesh_tool.py`, called by `scripts/analyze_scan.py` (`analyze-scan`) |
| `sys.path.append('/root/.claude/skills/...')` import pattern | not needed: the runtime runs scripts from their folder; see deliberate drops |
| Calculating mass: read ID, consult density table, Mass = Volume * Density | `analyze-scan` (lookup via `parse_density_table`), `compute-mass` |
| Units: volume is in coordinate units cubed | `main_part_volume` output description, `settle-units` instructions |
| Units: do not assume mm or inches; check the task's instructions for the coordinate unit | `settle-units` instructions and criteria; anti_pattern on unit conversion |
| Units: same unit as density table → multiply directly, no conversion | `same_as_table` criterion; `compute-mass` same_as_table branch |
| Critical note: binary support | `analyze-scan` description, `MeshAnalyzer._parse` |
| Critical note: 2-byte attribute extraction (color / material ID) | `analyze-scan` description, `_parse_binary` (`<12fH`) |
| Code: binary layout (80-byte header, uint32 count, 50-byte records, normal skipped, 3 vertices, `<H` attribute) | `_parse_binary` |
| Code: size-mismatch → ASCII fallback, ASCII IDs default 0 | `_parse`, `_parse_ascii`; warning in `mesh_report` |
| Code: signed volume via v1 · (v2 × v3), abs / 6 | `signed_volume`, `get_volume` |
| Code: vertex quantization to 5 decimals for connectivity | `get_components`, `analyze-scan` description |
| Code: sort components by volume, pick largest | `analyze_largest_component`; anti_pattern on triangle count |
| Code: material ID assumed uniform per component | majority vote + mixed-ID warning |
| Code: empty mesh → zero result | now raises (non-zero exit): an empty mesh has no part to weigh, and writing mass 0 would be a silent wrong answer |
| Code: `__main__` CLI printing the report | replaced by the step scripts' stdin/stdout JSON contract |
| Task: output format `{"main_part_mass": float, "material_id": int}` at the report path | `compute-mass` writes exactly these keys; anti_pattern on extra keys / types |
| Task: 0.1% accuracy | mass rounded to 4 decimals, no intermediate rounding |

## Deliberate drops

- **`sys.path.append('/root/.claude/skills/mesh-analysis/scripts')` example**: install-path specific; the AIP runtime launches scripts from `scripts/`, so `from mesh_tool import ...` resolves on its own.
- **`print(f"Volume: ...")` example lines**: illustrative only; the values are step outputs.
- **"Binary parse failed ... Falling back to ASCII" print**: stdout is reserved for the step's JSON output; the same information is a `mesh_report.warnings` entry.
