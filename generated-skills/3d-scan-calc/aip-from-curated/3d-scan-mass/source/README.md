# Provenance

This AIP skill was compiled from one curated Agent Skill:

- `source/mesh-analysis/` — original SKILL.md and `scripts/mesh_tool.py` for
  parsing binary STLs, running connected-component analysis, and extracting
  material IDs from the per-triangle attribute bytes.

Plus the task's environment data in `./inputs/environment/`:
- `material_density_table.md` — the lookup table shape (Material ID → name,
  density in g/cm³) the compute-mass step is written to parse.
- `scan_data.stl` — a representative input (a noisy binary STL whose main
  component has material_id `42` / Unobtanium, with debris carrying ids
  `0` and `1`), used only to shape the pack; the pack hardcodes no answer.

# How the sources map onto this pack

The curated skill described a single workflow:

1. Parse the binary STL.
2. Run connected-component analysis; pick the largest component as the main
   part (debris / dust / noise filter).
3. Read the material ID from the STL attribute bytes of that component.
4. Look up density in a supplied table.
5. Multiply volume × density to get mass, after making sure the units line
   up (density table is g/cm³).

That compiles cleanly into two execution steps and an end step:

- **`analyze-mesh`** (`execution`) — the mesh/geometry work. Wraps
  `MeshAnalyzer(stl_path).analyze_largest_component()` from `mesh_tool.py`
  and emits `volume_raw`, `material_id`, `total_components`. Deterministic
  numeric code → script, not a decision or client_task.
- **`compute-mass`** (`execution`) — unit conversion + table lookup +
  multiplication. Also deterministic numeric / tabular logic → script.
- **`end`** — declares `mass_grams`, `material_name`, `material_id`,
  `volume_cm3`, `density_g_per_cm3`, `total_components` as the terminal
  state.

The pipeline is linear, so no routers / decisions are needed. There is no
`client_task` because every judgment the curated skill called out (which
component is the main one, which material_id, which density row, how to
multiply) is deterministic once the inputs are in state.

The only piece of information that genuinely needs human / agent judgment
is the coordinate unit — the STL format does not record it. That is kept
as a required input in the initial state (`coord_unit`), documented in
the SKILL.md `purpose`, and consumed by `compute-mass` for the (unit)³ → cm³
conversion.

# `scripts/`

- `mesh_tool.py` — copied verbatim from
  `source/mesh-analysis/scripts/mesh_tool.py`. Imported by `analyze_mesh.py`.
- `analyze_mesh.py` — thin AIP wrapper around `MeshAnalyzer`; reads
  `currentState.stl_path`, prints the three required output keys.
- `compute_mass.py` — parses the Markdown density table, applies the
  `coord_unit`³ scale factor, looks up the material, multiplies.

# Deliberate drops

Items from the curated source that are intentionally not represented as
first-class pack content, with rationale:

1. **The ASCII-STL fallback branch in `_parse` / `_parse_ascii`.** The code
   is still present in `scripts/mesh_tool.py` (verbatim copy) and will fire
   automatically if the input is ASCII, so the behavior is preserved; it is
   just not promoted to an AIP step. The curated SKILL.md itself describes
   this skill as "Binary STL parsing", and the `do_not_use_when` list
   explicitly warns that ASCII STLs lose material IDs and this pack is not
   the right tool for them.
2. **The example `/root/.claude/skills/mesh-analysis/scripts` `sys.path`
   `append` snippet** from the source Usage section. That path is specific
   to how the mesh-analysis skill was previously installed; this pack
   bundles `mesh_tool.py` under its own `scripts/` and `analyze_mesh.py`
   adds its own folder to `sys.path`. The rewritten form carries the same
   intent — "import `MeshAnalyzer` from the bundled module".
3. **Prose "Basic Workflow" Python snippet** showing manual
   `print(f"Volume: ...")` output. Replaced by the structured JSON output
   of `analyze_mesh.py` that the AIP runtime consumes; the same values
   (volume, material id) are produced, just emitted as JSON instead of
   printed.
4. **Rationale commentary** ("Noise Filtering", "Attribute Extraction",
   "often used for color or material ID") — background describing *why*
   the tool exists. Not actionable at run time; the choice to filter noise
   and read the attribute bytes is already baked into
   `analyze_largest_component()` and the compute-mass lookup.

Every actionable rule, condition, threshold, lookup, and unit caveat from
the sources is represented in the body or in the scripts.

# Non-drops — where each actionable source item lives

- "Binary STL parsing" — `scripts/mesh_tool.py::_parse_binary`, called by
  `analyze_mesh.py`.
- "Connected component analysis" / "Noise Filtering" / largest-component
  selection — `MeshAnalyzer.get_components` + `analyze_largest_component`,
  invoked by `analyze_mesh.py`; `analyze-mesh` step description names it.
- "Attribute Extraction" of the 2-byte material ID — `_parse_binary`
  struct unpack of `data[48:50]`; carried out by `MeshAnalyzer` and
  surfaced as `material_id` by `analyze_mesh.py`.
- "Mass = Volume × Density" formula and "Ensure volume is in cm³ and
  density is in g/cm³" note from `material_density_table.md` —
  `compute_mass.py` performs the (coord_unit)³ → cm³ conversion and the
  multiplication. Formula echoed in the `compute-mass` step description.
- "Do not assume millimeters or inches. Check your task instructions for
  the coordinate system units" — surfaced in the SKILL.md `purpose` as a
  required `coord_unit` initial-state input, and reinforced in
  `anti_patterns`.
- "If your density table uses the same unit (e.g., g/cm³ and cm³),
  multiply directly. No unit conversion is needed." — covered by the
  cm→cm scale factor of 1.0 in `compute_mass.py`'s `UNIT_TO_CM` map; if
  the caller passes `coord_unit=cm`, no conversion is applied.
- Density table row shape (`| id | name | density | description |`) —
  parsed by `compute_mass.py::parse_density_table`, which keys on the
  first numeric cell and reads the third cell as density.
