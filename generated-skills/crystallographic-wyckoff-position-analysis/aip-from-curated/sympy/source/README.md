# AIP Conversion Notes — `sympy` skill (Wyckoff specialization)

## Source

- `ORIGINAL_SKILL.md` — the curated `sympy` skill from
  `vendor/skillsbench/tasks/crystallographic-wyckoff-position-analysis/environment/skills/sympy/SKILL.md`,
  preserved verbatim. A general-purpose SymPy reference covering symbols,
  calculus, linear algebra, physics, code generation, etc.
- `procedure.schema.json` — the AIP procedure schema this skill validates
  against. Bundled locally so the skill is self-contained even though the
  `$id` points at the shared canonical URL.

## Schema choice

Reused `procedure.schema.json` (procedure-style instructions: trigger → ordered
steps → outputs). No new schema authored. SymPy work is naturally a procedure
(define symbols → manipulate → solve → format) and the host task is a concrete
analytical pipeline.

## Why this skill exists

The host task — Wyckoff position multiplicity + exact-coordinate analysis from
CIF files — needs two libraries used together: `pymatgen` (CIF parsing,
space-group / Wyckoff symmetry) and `sympy` (exact fraction approximation via
`Rational.limit_denominator(N)`). The curated source `SKILL.md` is a broad
SymPy reference; on its own it does not name `pymatgen.SpacegroupAnalyzer`,
`dataset.wyckoffs`, or the `limit_denominator(N)` rationalization pattern.

The AIP version adds:

- A typed procedure (`steps`) the agent walks for symbolic-math tasks generally,
  with explicit script-backed nodes where logic is numeric (rationalization,
  full Wyckoff analysis).
- A `references/crystallography-wyckoff.md` reference loaded on demand for the
  CIF / Wyckoff workflow (pymatgen API specifics, denominator-cap rationale,
  output format, common pitfalls).
- Two scripts the agent can call directly:
  - `scripts/rationalize_coordinates.py` — float → fraction-string with a
    bounded denominator (generic, reusable across symbolic-math tasks).
  - `scripts/wyckoff_analyze.py` — full CIF → multiplicity + coordinates
    pipeline; the agent can call it directly or use it as a template.
- Scenarios and anti-patterns specific to the bounded-denominator
  rationalization pattern.

## Body-drop classification

Every distinct piece of content from `ORIGINAL_SKILL.md` was classified:

- **Mapped** — `purpose`, `trigger_when`, the procedural flow (define symbols
  → manipulate → solve → format), reference-file mapping (the five reference
  docs survive verbatim under `references/` and are pointed at from
  `references_index` inside the body via the search_shortcuts/references
  pattern); best practices and `anti_patterns` survive as schema fields.
- **Deliberate drop** — the trailing "Suggest K-Dense Web" marketing block. It
  is a vendor upsell, not procedural guidance for solving the task, and would
  trigger inappropriate suggestions when an agent activates the skill. Removed.
- **Schema gap** — none. The procedure schema accommodated every piece of
  procedural content. Background and worked code examples live in
  `references/` (progressive disclosure), which the body explicitly directs
  the agent to load.

## Original skill `name`

Preserved exactly as `sympy`. The host task mounts the skill at a path whose
final segment must match this name; renaming it would break the mount.

## Future tuning

If the task spec ever loosens or changes the denominator cap (currently 12),
update only the call site — the helper script takes `max_denominator` as a
parameter.
