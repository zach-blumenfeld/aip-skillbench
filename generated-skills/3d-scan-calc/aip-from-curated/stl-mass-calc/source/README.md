# stl-mass-calc — source materials

## Provenance

Compiled from the curated Agent Skill that ships with the SkillsBench task
`3d-scan-calc`. The task itself is at
`vendor/skillsbench/tasks/3d-scan-calc/` in this repo.

Files copied verbatim under `source/`:

- `mesh-analysis/SKILL.md` — the original mesh-analysis skill, copied from
  `vendor/skillsbench/tasks/3d-scan-calc/environment/skills/mesh-analysis/SKILL.md`.
- `mesh-analysis/scripts/mesh_tool.py` — the `MeshAnalyzer` implementation,
  copied from
  `vendor/skillsbench/tasks/3d-scan-calc/environment/skills/mesh-analysis/scripts/mesh_tool.py`.

The runtime copy of `mesh_tool.py` used by the AIP procedure lives at
`scripts/mesh_tool.py` in the skill root. It is byte-for-byte identical to the
source; keeping both makes provenance obvious and lets the runtime import the
module directly from the same folder as `analyze_mesh.py`.

The source skill only covers mesh analysis. The task additionally requires
looking up a density from `/root/material_density_table.md` (delivered by the
task Dockerfile) and writing a `mass_report.json`. The AIP skill compiles both
halves (mesh analysis + density lookup + mass calculation + report write) into
a single procedure so an agent can run it end-to-end.

The density table's markdown layout — `| **id** | name | density (g/cm^3) | description |`
— is domain context read from the task's `material_density_table.md`. The AIP
skill does not bundle the table itself (the caller passes it via
`density_table_path`, and the values may change per task), but
`compute_mass_report.py`'s parser matches this layout.

## Compiled procedure

Two `execution` steps and an `end`. State flow:

```
{stl_path, density_table_path, output_path}
      → analyze-mesh (execution, scripts/analyze_mesh.py)
+ {main_part_volume, material_id, total_components}
      → compute-mass-report (execution, scripts/compute_mass_report.py)
+ {main_part_mass, report_path, density}
      → end
```

`analyze-mesh` wraps `MeshAnalyzer.analyze_largest_component()` and returns
`main_part_volume`, `material_id`, and `total_components`.
`compute-mass-report` parses the markdown density table, resolves the density
for `material_id`, computes `mass = volume * density`, writes the JSON report
to `output_path`, and returns `main_part_mass`, `report_path`, and `density`.

## Step-kind choices

- **`analyze-mesh` — execution.** STL parsing, connected-component
  segmentation, signed-tetrahedron volume, and attribute-byte extraction are
  all deterministic numeric algorithms over structured input. Exactly what
  `execution` is for. The source `mesh_tool.py` already implements this; the
  runtime script is a thin JSON stdin/stdout wrapper around it.
- **`compute-mass-report` — execution.** Deterministic markdown-table parse,
  fixed lookup, single multiplication, and a file write. No judgment
  required, so no `decision` or `client_task`.
- **No `decision` steps.** Every branching point in the source workflow is
  numeric (largest by volume, density lookup by ID). Nothing needs LLM
  judgment.
- **No `client_task` steps.** The output is a fully specified JSON blob at a
  known path; no free-form text or synthesis to generate.
- **No `router`.** The graph is linear: analyze → compute → end.
- **Two scripts, not one.** Best practice favors fewer script files, but
  mesh analysis and the density-lookup + report-write are truly independent:
  the first is reusable domain logic mirroring the source skill; the second
  is task-specific glue that consumes only scalars. Splitting also keeps the
  mesh library importable on its own (`scripts/mesh_tool.py`) without pulling
  in density-table parsing.

## Line-by-line completeness check against `source/mesh-analysis/SKILL.md`

Walked every distinct piece of content in the source SKILL.md; each is
carried in the compiled body, in a script docstring, in `mesh_tool.py`, or
recorded here as a deliberate drop.

Carried:

- "Analyzes 3D mesh files (STL) to calculate geometric properties (volume,
  components) and extract attribute data" — captured in the compiled skill's
  `description` and `purpose`.
- "process noisy 3D scan data and filter debris" — captured in `purpose`,
  `trigger_when`, and the `analyze-mesh` step description.
- "MeshAnalyzer tool", Binary STL parsing, connected-component analysis —
  implemented by the runtime copy at `scripts/mesh_tool.py`; behavior
  documented in `analyze-mesh`'s `description`.
- "Geometric Analysis: Calculating volume of complex or noisy meshes",
  "Noise Filtering: Isolating the largest connected component", "Attribute
  Extraction: Extracting metadata (e.g. material IDs) stored in the STL file
  attribute bytes" — the three use cases are listed in `trigger_when`.
- `analyze_largest_component()` returning `main_part_volume` and
  `main_part_material_id` — these become `main_part_volume` and
  `material_id` on the state after `analyze-mesh` (the key was renamed from
  `main_part_material_id` to `material_id` for compactness; the source
  key is preserved inside `mesh_tool.py`).
- "The tool provides the Volume and Material ID. To calculate Mass: ... Mass
  = Volume * Density" — realized as the `compute-mass-report` step.
- "Read the Material ID from the analysis report" and "Consult your provided
  material reference data (e.g. density tables) to find the density" —
  realized as the `density_table_path` input plus the parser inside
  `compute_mass_report.py`.
- Critical Note on Units — "Volume returned is in the same units as the STL
  file's coordinates (cubed)", "Do not assume millimeters or inches", "If
  your density table uses the same unit ... multiply directly. No unit
  conversion is needed" — surfaced in `purpose`, in the `compute-mass-report`
  step description ("Does no unit conversion — length units in the STL must
  already match the density table's length units"), in `do_not_use_when`
  ("STL's coordinate units and the density table's length units differ and
  no unit conversion is provided upstream"), and in `anti_patterns`
  ("Assuming STL coordinates are millimeters or inches and converting").
- "Binary Support: The tool automatically handles Binary STL files" — the
  code path is preserved in `scripts/mesh_tool.py`; called out in
  `analyze-mesh`'s description.
- "Attribute extraction: The tool extracts the 2-byte attribute stored in
  the binary STL format (often used for color or material ID)" — described
  in `analyze-mesh`'s step description ("Material ID ... read from the first
  triangle's 2-byte attribute field").

Deliberately dropped:

- The Python usage snippet in the source SKILL.md ("Add skill path to
  sys.path", `sys.path.append('/root/.claude/skills/mesh-analysis/scripts')`,
  the `import mesh_tool` example, the `print` calls) — this is
  human-oriented library-usage documentation. The AIP procedure invokes
  `MeshAnalyzer` for the agent via `scripts/analyze_mesh.py`; the agent
  never needs to import the library itself. Not actionable inside the
  procedure.
- The specific example `/path/to/your/file.stl` — replaced by the typed
  `stl_path` input on `analyze-mesh`, which the caller supplies.
- The hard-coded install path `/root/.claude/skills/mesh-analysis/scripts` —
  dropped as an environment assumption. The AIP runtime resolves the script
  location from the skill folder, so no absolute path is needed.
