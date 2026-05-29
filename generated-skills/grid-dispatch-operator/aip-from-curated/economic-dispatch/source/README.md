# Source notes — economic-dispatch AIP conversion

## Origin
Compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/grid-dispatch-operator/environment/skills/economic-dispatch/`.

## Schema choice
`procedure.schema.json` (AIP procedure family) — the source skill describes a
multi-step optimization workflow (parse → build cost → build limits → build
reserves → balance → solve → format), which is a textbook procedure.

## Script vs prose decisions
Scripted in `scripts/economic_dispatch.py`:
- **build_cost** — deterministic if/elif over NCOST (3/2/1) with fixed coefficient indices.
  Pure mechanical mapping from MATPOWER columns to a cvxpy expression.
- **build_gen_limits** — mechanical Pmin/Pmax bounds with per-unit conversion.
- **build_reserves** — fixed constraint set (non-negativity, per-gen cap, capacity
  coupling, system minimum). Identical every time.
- **build_dispatch_report** — mechanical dict assembly + the operating-margin formula
  (Σ Pmax − Pg − Rg).

Left as prose:
- **add-power-balance** — branches on whether the network has transmission data.
  Choosing nodal DC-OPF vs. bulk single-bus balance is a judgment call about the
  problem at hand; expressed as `one_of` and delegated to `dc-power-flow` when nodal.
- **solve** — one cvxpy call, but the solver-choice rationale (CLARABEL > OSQP for
  ill-conditioned DC-OPF) is reasoning the agent needs to read.
- **load-network-data / declare-decision-variables** — boilerplate the agent writes
  inline alongside `power-flow-data`; scripting would just hide what's already obvious.

## Companion skills preserved
The source skill explicitly defers network-side modelling ("see dc-power-flow skill")
and parsing ("network data follows the MATPOWER format"). Those companions live in
the same task environment and are referenced via `integrations`. This skill owns
only the cost side, generator bounds, reserves, and dispatch output formatting.

## Deliberate drops
None. Every section of the source SKILL.md and the cost-functions reference is
either mapped into a step body, captured as anti-pattern guidance, or preserved
under `references/`.
