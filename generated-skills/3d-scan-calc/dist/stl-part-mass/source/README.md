# Provenance

Compiled from the curated skill `mesh-analysis` (copied verbatim in `mesh-analysis/`:
`SKILL.md`, `scripts/mesh_tool.py`) for the task "mass of the main part of a scanned binary
STL whose attribute bytes hold a Material ID, using a markdown density table, written to a
JSON report". Functional-tested against the real task inputs (`scan_data.stl`, 352 triangles,
53 components; `material_density_table.md`) plus synthetic variants (internal void, mixed IDs,
unknown ID, trailing bytes, ASCII, mm scale).

# Component kinds

| Component | Kind | Why |
|---|---|---|
| Read task + table | client_task | Free-text reading of task-specific paths, output keys, units. |
| Inspect mesh (`mesh_mass.py analyze`) | execution | Parsing, components, volume, edge checks are deterministic code. |
| `coordinate_units` | decision (choice) | Unit statement must be judged from task text; answer space is fixed; maps to a numeric `--volume-scale`. |
| `subtract_voids` | decision (noul) | Whether flagged shells are cavities depends on task wording; script flags candidates. |
| `selection_ok` | decision (noul) | Whether warnings invalidate the main-part pick needs judgement; script raises the warnings. |
| Compute mass (`mesh_mass.py mass`) | execution | Table lookup, multiplication, scaling, JSON write are deterministic. |
| Verify output | client_task | Matching the task's exact output format. |

One script (`scripts/mesh_mass.py`) replaces `mesh_tool.py`; it keeps the `MeshAnalyzer` API
(`analyze_largest_component`, `get_components`, `get_volume`) and the same algorithms
(binary-first with size check, ASCII fallback with ID 0, shared-vertex BFS with 5-decimal
rounding, |Σ v1·(v2×v3)|/6, largest by volume). Changes: majority Material ID instead of first
triangle (identical for uniform parts, robust to stray triangles); trailing-byte tolerance;
edge/orientation check, void/ambiguity warnings, `--component I` override; density-table parsing and mass/JSON output
(the original left these to the agent); stdlib only since the container has no numpy.

# Deliberate drops

- Original hard-coded `sys.path.append('/root/.claude/skills/mesh-analysis/scripts')`: install
  path differs; replaced by a CLI and a relative-path import note.
- Original's "Binary parse failed ... Falling back to ASCII" print: replaced by a format line and
  explicit warnings.
- Prose "When to Use" bullets: merged into Trigger When / description, not dropped in substance.
