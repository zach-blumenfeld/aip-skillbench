# source/ — provenance

## What was compiled

This AIP skill, `3d-scan-mass-calc`, was compiled from a single curated Agent
Skill:

- `mesh-analysis/` — original SKILL.md + `scripts/mesh_tool.py`, copied
  verbatim from `inputs/skills/mesh-analysis/` in the authoring input set.

That skill ships only the **MeshAnalyzer tool** (parse binary STL, isolate
largest connected component, extract 2-byte attribute as material_id, compute
signed-tetrahedron volume). The surrounding workflow — unit handling, density
lookup, mass computation — was described in its SKILL.md body as instructions
to a human caller; this compilation turns that into typed, enforced steps.

## Target environment

Per `inputs/environment/Dockerfile`, scripts run on Ubuntu 24.04 with
`python3` + `python3-pip` only. `mesh_tool.py` uses stdlib (`collections`,
`os`, `struct`); the two AIP wrapper scripts also use stdlib. Nothing extra
needs to be installed.

## Step-kind choices

Three steps total — a linear graph, no router (the workflow has no genuine
branch point: debris filtering is unconditional, mass computation always runs).

- **`analyze-mesh` → execution.** Parsing a binary STL, running connected
  components, summing signed tetrahedra, selecting the largest component by
  volume — all deterministic logic over structured input. Correctly a script.

- **`lookup-density` → client_task.** The density table is a markdown file
  whose exact layout varies across tasks (plain table, nested headings, inline
  prose). Writing a brittle parser was rejected; the agent reads it with
  judgment, normalizes units to g/cm³, and emits one float. The template
  pins the output shape so the next script is unambiguous. A decision step
  is wrong here because the answer is a continuous value, not a label.

- **`compute-mass` → execution.** Unit conversion from `stl_coord_unit`³ to
  cm³ and multiplication by density is a pure numeric calculation with a
  small lookup table (unit → cm). Scripted so the arithmetic is traceable
  and the conversion factors cannot drift.

## Deliberate-drop log

Content from the source SKILL.md that was not carried verbatim into the AIP
body, with rationale. Rules, numeric thresholds, unit handling, and the
material-ID extraction behavior are **not** on this list — they are all in
`SKILL.md`, `scripts/`, `assets/`, or `references/`.

- **Python usage example that `sys.path.append`s `/root/.claude/skills/...`.**
  The AIP runtime invokes `scripts/analyze_mesh.py` directly as a step; the
  script sits next to `mesh_tool.py` and imports it from the same directory
  (via a `sys.path.insert(0, ...)` for the script's own folder). The caller
  never writes the glue code, so the example is non-actionable in this form.
  The underlying behavior — `MeshAnalyzer(path).analyze_largest_component()`
  returning `main_part_volume` + `main_part_material_id` — is captured
  verbatim in `scripts/analyze_mesh.py`.

- **Prose "## Critical Notes" bullets** on binary support and attribute
  extraction. These describe internals of `MeshAnalyzer`; the behavior is
  preserved by using the original `mesh_tool.py` unmodified. The user-facing
  consequence (binary STL carries material_id, ASCII does not) is in the
  anti-patterns list in `SKILL.md`.

- **"How to compute mass" bullet list** in the source body (read material_id,
  consult density table, Mass = Volume × Density). This is now the whole
  shape of the AIP procedure — split into `lookup-density` and
  `compute-mass` steps rather than left as prose for the agent to execute.
