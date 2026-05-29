# Source notes — economic-dispatch (AIP conversion)

## Intent

This is an AIP conversion of the curated Agent Skill at:
`vendor/skillsbench/tasks/energy-market-pricing/environment/skills/economic-dispatch/`

The original `SKILL.md` is preserved verbatim at `SKILL.original.md` for
reference and traceability.

## Schema choice

Validates against the bundled `procedure.schema.json` — this skill is a
procedure: a graph of script-backed steps (load → declare → cost →
limits → balance → reserves → solve → margin → format) with optional
branches (`one_of` on the balance step) and worked scenarios. No new
schema needed.

## Script consolidation

The original SKILL.md presented seven distinct Python snippets:

1. MATPOWER index/bus-mapping pattern
2. Cost expression with NCOST branching
3. Generator limits in per-unit
4. System power balance
5. Reserve co-optimization with capacity coupling
6. Operating-margin calculation
7. Dispatch + totals output formatting

These are not independent jobs — they are the layers an agent stacks
into one cvxpy Problem. AIP best practice says favor fewer script files
for simplicity, so the conversion collapses all seven into a single
library file: `scripts/dispatch_helpers.py`. Each step in the AIP body
names the function it calls in its description.

## Content classification

Walked the source SKILL.md line-by-line against the compiled AIP body:

- **Mapped (captured faithfully):**
  - MATPOWER `gen` index table → load-network step + helper that wraps
    the indices into a structured dict
  - MATPOWER `gencost` index table + NCOST 2/3 branching → build-cost
    step backed by `build_cost`
  - Generator limits per-unit conversion → add-generator-limits step
  - System power balance → add-power-balance step's `system_balance` arm
  - "Use nodal balance instead" guidance → add-power-balance step's
    `nodal_balance_from_dc_power_flow_skill` arm + integrations entry
  - Reserve variables, capacity coupling, system requirement → reserve
    step backed by `reserve_cooptimization` (also exposes the system
    constraint so the dual / reserve MCP is reachable — a small lift
    beyond the original snippet, which omitted the MCP path)
  - Operating-margin definition → compute-operating-margin step + helper
  - Dispatch list + totals output format → format-output step + helpers
  - CLARABEL solver guidance and OSQP warning → solve step description
    + anti-pattern

- **Deliberate enhancements (not in source, added for the task):**
  - `system_reserve_constraint` is now an explicit output of the reserve
    step so an agent doing market clearing can read the reserve MCP from
    its dual. The source SKILL.md described the reserve constraint but
    did not name it as a hand-back.
  - Integration with dc-power-flow is spelled out as an explicit
    integration entry, plus an LMP / binding-line scenario derived from
    the parent task's market-report shape. The source mentioned
    composition only in passing.
  - Anti-patterns list compiles the gotchas that were scattered through
    the source prose (per-unit, NCOST branching, OSQP, bus mapping,
    operating-margin definition, "don't add both balances").

- **Deliberate drops:** none. Every Python snippet in the source maps to
  a function in `dispatch_helpers.py`.

## References kept

`references/cost-functions.md` is copied verbatim. The body points the
agent at it for the full MATPOWER polynomial-type-2 format, marginal-cost
identities, the piecewise-linear cost variant (not exercised by the main
task but worth keeping in scope), and typical coefficient ranges by
generator type.

## Name lock

`name: economic-dispatch` is unchanged — the parent task mounts this
skill folder by name and the task definition would not pick it up under
any other slug.
