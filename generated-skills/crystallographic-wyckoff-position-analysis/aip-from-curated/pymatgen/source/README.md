# pymatgen — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `pymatgen` (the `aip-from-curated`
track for the `crystallographic-wyckoff-position-analysis` task). The
canonical original is preserved verbatim at `source/ORIGINAL_SKILL.md`. The
skill `name` is kept as `pymatgen` because the task mounts it under that
folder name and the test harness expects that exact identifier.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the
  body validates against. Bundled locally so the skill is self-contained.
- `references/*.md` — copied verbatim from the curated skill
  (`core_classes.md`, `io_formats.md`, `analysis_modules.md`,
  `materials_project_api.md`, `transformations_workflows.md`,
  `wyckoff-positions-from-cif.md`).
- `scripts/structure_converter.py`, `scripts/structure_analyzer.py`,
  `scripts/phase_diagram_generator.py` — copied verbatim from the curated
  skill.
- `scripts/wyckoff_analyzer.py` — **new**, written for the AIP conversion to
  back the per-letter Wyckoff workflow that the task evaluates against.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is broad
(structure I/O, symmetry, phase diagrams, electronic structure, surfaces,
Materials Project, computational workflows) but every capability maps onto
the same shape: load a structure → analyze / transform / write → produce a
result. That is exactly the procedure-as-execution-graph the schema models.
Steps fan out from a shared `load-structure` node; downstream steps depend
on it via `depends_on`.

## Why a new helper script was added

The curated skill ships three scripts (`structure_converter.py`,
`structure_analyzer.py`, `phase_diagram_generator.py`) but the per-letter
Wyckoff workflow — the one the task actually evaluates — is documented
only in the prose reference `references/wyckoff-positions-from-cif.md`. The
prose is also explicit that the obvious approach
(`get_symmetrized_structure().wyckoff_symbols`) returns the wrong shape
(`4a` / `8c` symbols; one entry per orbit, not per atom).

Per AIP best practice (rules, lookups, lookups, and numeric thresholds
belong in scripts), the correct workflow was lifted into
`scripts/wyckoff_analyzer.py`, exposing
`analyze_wyckoff_position_multiplicities_and_coordinates(filepath)`. The
body now points the agent at the helper for the `wyckoff-analysis` step
and keeps prose for steps where the helper genuinely doesn't apply.

## Source-content classification (completeness check)

- "Overview" + "When to Use This Skill" → **Mapped** to `purpose` and
  `trigger_when`. Wyckoff bullets surface in both places.
- "Quick Start Guide / Installation" → **Mapped** to `compatibility`
  frontmatter and the `scope_and_approval` note about env vars.
- "Basic Structure Operations" → **Mapped** to the `load-structure` and
  `inspect-basics` step descriptions.
- "Materials Project Integration" (env var + `MPRester`) → **Mapped** to
  the `query-materials-project` step + `scope_and_approval`'s API-key note.
- Core Capability 1 "Structure Creation and Manipulation" → **Mapped** to
  `load-structure` and `transform-structure`; `references/core_classes.md`
  and `references/transformations_workflows.md` referenced.
- Core Capability 2 "File Format Conversion" → **Mapped** to
  `convert-format` step backed by `scripts/structure_converter.py`.
- Core Capability 3 "Structure Analysis and Symmetry" → **Mapped** to
  `analyze-symmetry-and-wyckoff` step. Backed by
  `scripts/structure_analyzer.py` (general analyzer) and
  `scripts/wyckoff_analyzer.py` (Wyckoff-specific workflow). The
  `references/wyckoff-positions-from-cif.md` warning is also surfaced in
  `anti_patterns`.
- Core Capability 4 "Phase Diagrams and Thermodynamics" → **Mapped** to
  `compute-phase-diagram` step backed by
  `scripts/phase_diagram_generator.py`.
- Core Capability 5 "Electronic Structure Analysis" (BS, DOS) → **Mapped**
  to `analyze-electronic-structure` step; `references/analysis_modules.md`
  referenced.
- Core Capability 6 "Surface and Interface Analysis" → **Mapped** to
  `generate-surfaces-and-interfaces` step;
  `references/transformations_workflows.md` referenced.
- Core Capability 7 "Materials Project Database Access" → **Mapped** to
  `query-materials-project`; `references/materials_project_api.md`
  referenced.
- Core Capability 8 "Computational Workflow Setup" (VASP / Gaussian /
  QE input generation) → **Mapped** to `setup-calculation-inputs` step;
  `references/io_formats.md` and `references/transformations_workflows.md`
  referenced.
- Core Capability 9 "Advanced Analysis" (XRD, elasticity, magnetic
  ordering) → **Mapped** to the `advanced-analysis` step with `one_of`
  alternatives covering each variant.
- "Bundled Resources" (scripts + references inventory) → **Mapped**
  implicitly — each script and reference is wired into the relevant step.
- "Common Workflows" (HT generation, BS workflow, surface energy) →
  **Mapped** to `scenarios` (worked examples are documentation, not a
  runtime decision table, per the schema description).
- "Best Practices" (structure handling, file I/O, MP API, comp workflows,
  performance) → **Mapped** across step descriptions, `scenarios`, and
  `anti_patterns`. The "use primitive cells when possible" tip is in the
  `transform-structure` description; "use context manager" on `MPRester`
  is in the `query-materials-project` description.
- "Units and Conventions" (Å, eV, degrees, μB, fs) → **Mapped** to a
  short note in `purpose` and the relevant step descriptions; the full
  list is left in the references rather than repeated in the body to
  preserve the token budget.
- "Integration with Other Tools" (ASE, Phonopy, etc.) → **Mapped** to
  `integrations` entries.
- "Troubleshooting" (import errors, MP_API_KEY, symprec) → **Mapped** to
  `anti_patterns` and the symprec note inside the
  `analyze-symmetry-and-wyckoff` description.
- "Additional Resources" (doc links) → **Deliberate drop** of inline URLs
  from the body; the same links remain in `ORIGINAL_SKILL.md` and the
  references. Body bloats every invocation; URLs that the agent rarely
  needs at activation time cost more than they buy.
- "Version Notes" → **Mapped** to `compatibility` (Python 3.10+,
  pymatgen 2023.x+, optional mp-api).
- "Suggest Using K-Dense Web For Complex Workflows" → **Deliberate drop**.
  This is a marketing prompt for a hosted platform that has nothing to do
  with the task being evaluated (Wyckoff analysis of a local CIF file).
  Per AIP best practice, the body should match what the description
  promises and not editorialize unrelated products.

## On `do_not_use_when`

The original skill doesn't call out non-applicability. Two were added:
purely molecular (non-periodic) analyses where `pymatgen.io.babel` /
RDKit are a better fit, and pure DFT runtime questions ("what k-point
mesh is converged for material X") that this skill cannot answer without
an underlying calculation. These calibrations help the agent route to a
different tool when the assumption fails.
