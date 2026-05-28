# source/

Canonical inputs used to compile this AIP skill.

- `SKILL.original.md` — the curated (non-AIP) skill copied verbatim from
  `vendor/skillsbench/tasks/drone-planning-control/environment/skills/motor-model-dynamics/SKILL.md`.
- `procedure.schema.json` — bundled copy of the AIP `procedure` schema
  (`$id`: `https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json`)
  used to validate `../SKILL.md`. The skill is self-contained even though the
  `$id` points to a shared canonical URL.

## Schema choice

The source describes a step-wise simulation procedure: build allocation matrix
→ solve desired RPMs → apply motor lag → compute actual force/moment →
assemble state derivative → integrate with RK45. The `procedure` schema is the
natural fit; no new schema needed.

## Mapping notes (source → AIP body)

- Overview / two-module framing → `purpose`.
- "Use this skill when …" (frontmatter description) → `description` + `trigger_when`.
- Motor Model "Propeller Allocation Matrix" table → `steps[build-allocation-matrix].description`
  (kept as a code-block matrix inside a block scalar so the column layout survives).
- Motor Model "Implementation Logic" steps 2–5 → `steps` solve-desired-rpms,
  apply-motor-lag, compute-actual-force-moment.
- Dynamics "State vector" table + "Implementation Logic" → `steps[assemble-state-derivative].description`.
- "RK45 Integration" section → `steps[rk45-integration]`.
- "Motor Physical Limits" parameter table → `search_shortcuts[Motor physical limits]`.
  Constants are reference lookups, not procedural steps; the `{category, body}`
  envelope preserves the table layout.
- "Max Thrust Calculation" formulas → `search_shortcuts[Max thrust and acceleration formulas]`.
  Same rationale — derived reference formulas, not a step to execute every run.
- Clamp/clip rules called out inside "Implementation Logic" step 3 → also surfaced
  in `decisions` so the agent picks them up when motor saturation is the signal.

## Deliberate drops

None — every distinct piece of the source SKILL.md is mapped above.
