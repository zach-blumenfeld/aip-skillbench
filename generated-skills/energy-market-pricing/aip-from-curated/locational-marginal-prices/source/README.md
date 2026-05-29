# locational-marginal-prices — AIP Author Notes

## Source

Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/energy-market-pricing/environment/skills/locational-marginal-prices/SKILL.md`
(see `SKILL.original.md`). Skill is consumed by the `energy-market-pricing`
SkillsBench task, where the agent must DC-OPF + reserve co-optimize a
MATPOWER network, extract LMPs, identify binding lines, then re-solve a
counterfactual that scales the line-64 <-> 1501 thermal rating by 1.20 and
emit a `report.json` with base, counterfactual, and impact_analysis blocks.

## Schema choice

Picked `procedure.schema.json` (bundled at `procedure.schema.json`). The
source SKILL is a mix of conceptual prose and Python snippets, but the
deliverable is procedural: wire constraint refs -> solve -> extract duals
-> assemble snapshot -> perturb -> re-solve -> compute impact -> emit
report. Each is a discrete script-backed node with typed inputs and outputs.
The conceptual material (sign convention, economic intuition) moves to
`references/pricing-concepts.md` and loads on demand.

No new schema drafted — schema reuse over invention per AIP best practices.

## Script vs prose decisions

Scripted (deterministic, mechanical — `scripts/lmp_utils.py`):
- `extract_lmps` — read dual_value, multiply by baseMVA, package as
  `{bus, lmp_dollars_per_MWh}`. Pure mechanical; the only risk in the
  source code is forgetting the baseMVA factor, which is exactly the kind
  of bug a script eliminates.
- `extract_reserve_mcp` — read dual_value, no scaling. Trivial but
  separate from LMP so the no-scale rule is enforced.
- `find_binding_lines` — flow computation, 99% threshold, status / x / rate
  filters. Fixed formula, fixed threshold — exactly scriptable.
- `perturb_line_limit` — copy + scale + raise on miss. Mechanical lookup
  with bidirectional match.
- `compute_impact_analysis` — fixed arithmetic, fixed ranking rule
  (most-negative delta), fixed `congestion_relieved` predicate. Pure
  reduction over the two snapshots.

Prose (judgment / orchestration):
- `wire-balance-constraint-refs` / `wire-reserve-constraint-ref` — these
  must happen INSIDE the caller's economic-dispatch problem construction;
  this skill can't script around someone else's variable structure.
- `solve` — the caller picks the solver and decides when to bail on a
  non-optimal status; we just note the precondition.
- `assemble-case-snapshot` / `assemble-report` — trivial dict packing the
  agent will do inline; a script would add a file dependency without
  saving any logic.
- `resolve-counterfactual` — orchestration of "do steps 1-7 again on
  perturbed data", which is exactly the kind of cross-cutting reasoning
  the agent should drive, not a script.

## Mapping the source content

| Source section                                | Destination                                                |
|-----------------------------------------------|------------------------------------------------------------|
| Definition of LMP as dual of balance          | `purpose` + `references/pricing-concepts.md` § 1           |
| "Store balance constraints, solve, read duals"| `wire-balance-constraint-refs` + `extract-lmps`            |
| `extract_lmps` Python snippet                 | `scripts/lmp_utils.py::extract_lmps`                       |
| `* baseMVA` per-unit scaling rule             | `extract-lmps` description + anti_pattern + reference § 1  |
| LMP sign convention (pos vs neg)              | `references/pricing-concepts.md` § 2 + negative-LMP scenario|
| Negative LMP "not an error" note              | reference § 2 + anti_pattern                               |
| Reserve MCP snippet                           | `scripts/lmp_utils.py::extract_reserve_mcp` + `extract-reserve-mcp` |
| Reserve MCP semantics ("$/MWh of capacity")   | reference § 3                                              |
| Binding-line snippet                          | `scripts/lmp_utils.py::find_binding_lines` + `find-binding-lines` |
| `BINDING_THRESHOLD = 99.0`                    | `scripts/lmp_utils.py::BINDING_THRESHOLD_PCT`              |
| Counterfactual workflow (4 steps)             | `perturb-line-limit` + `resolve-counterfactual` + `compute-impact` |
| Branch-modification snippet (both orientations)| `scripts/lmp_utils.py::perturb_line_limit`                |
| `cost_reduction = base - cf`                  | `scripts/lmp_utils.py::compute_impact_analysis`            |
| "Negative delta = price decreased"            | reference § 6 + ranking anti_pattern                       |
| `congestion_relieved` predicate               | `scripts/lmp_utils.py::compute_impact_analysis` + reference § 5 |
| Economic intuition (3 bullets at end)         | `references/pricing-concepts.md` § 5                       |
| Cross-reference to `dc-power-flow`            | `do_not_use_when` (avoids duplication; flow math lives there)|

### Deliberate drops

- None. The source SKILL is small; every concept lands somewhere in the
  AIP version. Snippets are absorbed into `lmp_utils.py`; conceptual text
  is split between `purpose`, step descriptions, scenarios, anti_patterns,
  and the on-demand reference.

## Extensions beyond the source

The source did not explicitly cover:

- **Top-N ranking for `buses_with_largest_lmp_drop`.** The source shows the
  per-bus delta computation; the task's `report.json` schema requires the
  top 3 by most-negative delta. Encoded in `compute_impact_analysis` with
  deterministic tie-break by bus number.
- **The full `report.json` assembly.** The source stops at "compute impact";
  the task asks for a specific JSON shape. Added `assemble-case-snapshot`
  and `assemble-report` prose steps so the agent doesn't drift on field
  names or wrap the blocks in an extra envelope.
- **`status == 0` filtering on branches.** Standard MATPOWER hygiene from
  the sibling `power-flow-data` skill; folded into `find_binding_lines` to
  avoid out-of-service branches showing up as "overloaded".
- **Error on missing target branch in `perturb_line_limit`.** The source
  uses `break` (silent no-op on miss). A typo would invalidate the entire
  counterfactual, so the script raises instead.

These extensions are mechanical extrapolations from the task spec
(`instruction.md`) and standard PGLib/MATPOWER conventions, not new
opinions on pricing methodology.
