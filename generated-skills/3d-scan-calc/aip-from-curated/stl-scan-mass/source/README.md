# Provenance — stl-scan-mass

Compiled from one curated Agent Skill, copied verbatim under `source/mesh-analysis/`:

- `mesh-analysis/SKILL.md`: when/how to use the `MeshAnalyzer` tool and the mass recipe
  (Mass = Volume × Density, plus the units warning).
- `mesh-analysis/scripts/mesh_tool.py`: binary/ASCII STL parser, connected components,
  signed-tetrahedron volume, largest-component report.

Target environment (from the task's Dockerfile): `ubuntu:24.04` with bare `python3` and pip,
no numpy/trimesh. The inputs are a binary STL whose 80-byte header reads "Binary STL with
proprietary Material IDs" and whose per-triangle uint16 attribute holds material IDs (several
IDs, including 0, appear in the file), plus a markdown density table
(`| Material ID | Material Name | Density (g/cm³) | Description |`, IDs in `**bold**`) whose
note says volume must be in cm³. All scripts are standard-library only and were checked to
parse files of that exact format.

## Intent

Given an STL scan and a material density table, compute the mass of the main part:
isolate the largest connected component (the rest is debris), read its material ID, look up
the density, put volume and density in the same unit, multiply.

## Graph and step-kind choices

| Step | Kind | Why |
|---|---|---|
| `analyze-mesh` | execution | Parsing, component splitting, volume, attribute histogram are deterministic geometry. |
| `compute-mass` | execution | Table lookup, unit conversion, multiplication, and the rules that flag anomalies are fixed rules over structured input. |
| `check-mass` | router | Branches on the script's `mass_status` (`ok` / `needs_review`). No judgment needed. |
| `resolve-material` | client_task | Only reached on anomalies (ID not in table, ID 0, ASCII file, debris-labelled material, mixed IDs, open shell, near-equal second component, unknown units). Fixing them needs the task's wording, which only the agent has; its output is overrides, and `compute-mass` recomputes, so the agent never types a mass. Loops back to `compute-mass`. |
| `report-answer` | client_task | The output location/format/rounding is task-specific text the agent must produce. |
| `end` | end | Mass and unit as computed, plus where and how (value, unit) it was reported. |

No `decision` step: in the normal path every judgment is deterministic. The open-ended
anomaly cases don't fit a fixed answer space (the fix is an override value), so they're a
client task rather than a choice question.

## Deliberate changes to the source tool (`scripts/mesh_tool.py`)

1. **Material ID = dominant non-zero attribute of the component**, not the first triangle's.
   The attribute is per triangle; an unset 0 on the first triangle would otherwise pick the
   wrong (or no) material. Mixed non-zero IDs are flagged for review.
2. **Parse warnings go to a list/stderr**, not `print()` to stdout (stdout is the step's JSON).
3. **Union-find for components** (same connectivity rule: shared vertex, coordinates rounded
   to 5 decimals): linear time on large scans; the original BFS is equivalent.
4. **Added a per-component report** (volume, triangle count, material ID,
   attribute histogram, open-edge count, bounding box) so anomalies can be reviewed.
5. Public API kept: `MeshAnalyzer(path).analyze_largest_component()` and the CLI
   (`python3 mesh_tool.py file.stl`) return the same three keys.

## Completeness walk (source → pack)

| Source item | Where in pack |
|---|---|
| Description: geometric properties, components, attribute data, noisy scans, debris | frontmatter `description`, `purpose`, `trigger_when` |
| When to use 1: volume of complex/noisy meshes | `trigger_when`, `analyze-mesh` |
| When to use 2: largest connected component isolates the part from dirty scan data | `analyze-mesh` script; anti-patterns (sum all / triangle count); `references/stl-format.md` § Components |
| When to use 3: material IDs from STL attribute bytes | `analyze-mesh` (`main_part_material_id`, histogram); reference § Binary layout |
| Usage: module in `scripts/`, `sys.path.append`, `MeshAnalyzer`, `analyze_largest_component`, `main_part_volume`, `main_part_material_id` | `scripts/mesh_tool.py` (same API); reference § By hand |
| Mass step 1: read material ID | `compute-mass` input `main_part_material_id` |
| Mass step 2: consult density table | `compute-mass` (parses markdown/CSV, bold IDs, unit from header) |
| Mass step 3: Mass = Volume × Density | `compute-mass` |
| Units: volume is STL coordinate units cubed | `compute-mass` docstring, `analyze-mesh` input description, reference § Volume |
| Units: do not assume mm or inches; take unit from task | `coordinate_unit` input description; anti-pattern |
| Units: same unit → multiply directly, no conversion | `compute-mass` (factor 1.0; `unspecified` → assume table's unit with a note); anti-pattern on double conversion |
| Critical note: binary handled automatically | `mesh_tool._parse_binary` (size rule); reference |
| Critical note: 2-byte attribute, used for color or material ID | reference § Binary layout |
| Code: binary first, size check `84+50N`, ASCII fallback with ID 0 | `mesh_tool._parse`; ASCII case flagged for review |
| Code: signed tetrahedron volume, `abs(sum)/6` | `mesh_tool.signed_volume/get_volume`; reference |
| Code: quantize to 5 decimals for vertex sharing | `mesh_tool.get_components`, `open_edge_count` |
| Code: sort components by volume, take largest | `mesh_tool.component_report` |
| Code: empty mesh → zero volume, 0 components | `mesh_tool.analyze_largest_component`; `analyze-mesh` flags "no triangles" |
| Code: material from first triangle | **changed**, see Deliberate changes #1 |
| Code: `__main__` CLI | kept in `scripts/mesh_tool.py` |

Added beyond the source (the knowledge a solver needs that the source left implicit):
review flags for debris-labelled materials, ID 0, open shells, and a near-equal second
component; unit conversion for mm/cm/m/in/ft and g/kg/lb density units; and an explicit
reporting step that follows the task's format, without rounding intermediate values.

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| Hard-coded path `/root/.claude/skills/mesh-analysis/scripts` in the usage example | Install path differs per environment; the reference uses `<skill>/scripts`, and step scripts import `mesh_tool` from their own folder. |
| `print(f"Volume: …")` example lines | Illustrative only; the state carries the values. |
| "e.g. if coordinates are in cm, volume is in cm³" example sentence | Rule is carried; example is redundant with the conversion logic. |
