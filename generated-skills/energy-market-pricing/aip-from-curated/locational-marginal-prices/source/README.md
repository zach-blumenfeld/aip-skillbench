# locational-marginal-prices — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `locational-marginal-prices` (the
`aip-from-curated` track for the `energy-market-pricing` task). The canonical
original is preserved verbatim at `source/ORIGINAL_SKILL.md`. The curated
skill shipped no code, so a helper module `scripts/lmp_ops.py` was authored
to back the procedure steps.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md` from
  `vendor/skillsbench/tasks/energy-market-pricing/environment/skills/locational-marginal-prices/SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the
  body validates against. Bundled locally so the skill is self-contained.
- `scripts/lmp_ops.py` — new helper module that encodes the prose-only
  rules from the original (parallel `balance_constraints` list, per-unit
  `* baseMVA` scaling, preserve negative duals, 99 %-loading threshold,
  bidirectional from/to lookup) as callable functions.

## Schema choice

`procedure` schema (reused, not drafted). The skill is a small execution
graph for market-clearing analysis: build → solve → extract LMPs / reserve
MCP / binding lines → modify line → solve counterfactual → re-extract →
compute impact → assemble report. That maps cleanly onto script-backed step
nodes connected by inputs / outputs, with `depends_on` capturing the
explicit base → counterfactual ordering.

## Why a helper script was added

The curated `SKILL.md` is prose + inline Python snippets — no `scripts/`
directory. The bulk of its content is rules that are best enforced in code,
not prose:

- "Store balance constraint references before solving" — without the
  parallel list, duals are unreachable. Encoded as the `extract_lmps`
  call contract.
- "Multiply by `baseMVA` to convert per-unit dual → $/MWh." Encoded inside
  `extract_lmps`.
- "Negative LMPs are physically valid — do not clip." Encoded by simply
  preserving sign in `extract_lmps`; called out in the docstring and the
  step description.
- "`BINDING_THRESHOLD = 99.0`" — a numeric threshold. Encoded as
  `DEFAULT_BINDING_THRESHOLD_PCT` in `lmp_ops.py`.
- "Skip branches with `x == 0` or `rate > 0`" — guard logic, encoded in
  `find_binding_lines`.
- "Match either `from→to` or `to→from`" — bidirectional lookup, encoded
  in `modify_line_limit` and in the `_is_target_line` predicate used by
  `compute_impact`.
- "Compute LMP delta per bus and surface the largest drops" — numeric
  pipeline with a `top_n` parameter, encoded in `compute_impact`.
- "`congestion_relieved` iff line was binding in base but not in CF" —
  conditional rule, encoded in `compute_impact`.

Per AIP best practice (steps with calculations, lookups, or numeric
thresholds belong in scripts), these rules were lifted into `lmp_ops.py`.
The body now describes the graph; the helper enforces the discipline. The
remaining prose in step descriptions covers what the helper cannot know —
WHICH bus pair to relax, which solver to use, and the per-unit-vs-MW
modelling choice the agent is making at problem-build time.

## Source-content classification (completeness check)

- Header "LMPs are the marginal cost of serving one additional MW of load at
  each bus … they are the dual values (shadow prices) of the nodal power
  balance constraints" → **Mapped** to `purpose` and the
  `build-and-store-balance-constraints` step.
- "To extract LMPs you must: 1) store references, 2) solve, 3) read duals"
  → **Mapped** to the three steps `build-and-store-balance-constraints`,
  `solve-base-case`, `extract-lmps-base`, and to the leading anti-pattern.
- Code block: `balance_con = pg_at_bus - pd == B[i, :] @ theta; balance_constraints.append(balance_con); constraints.append(balance_con)`
  → **Mapped** verbatim into the step description.
- `dual_val = balance_constraints[i].dual_value; lmp = float(dual_val) *
  baseMVA if dual_val is not None else 0.0; round(lmp, 2)` → **Mapped**
  inside `extract_lmps` (per-unit scaling, None guard, rounding).
- "Positive LMP / Negative LMP" sign-convention section → **Mapped** into
  the `extract-lmps-base` step description, the third scenario ("why are
  some LMPs negative?"), and the anti-pattern against clipping.
- "Negative LMPs commonly occur when … cheap generation trapped behind a
  congested line / adding load relieves congestion / magnitudes can be
  thousands of $/MWh in heavily congested networks" → **Mapped** to the
  third scenario's action and outcome lines.
- Reserve MCP code block (`reserve_con = cp.sum(Rg) >= reserve_requirement;
  reserve_mcp = float(reserve_con.dual_value)`) → **Mapped** to
  `build-and-store-reserve-constraint` + `extract-reserve-mcp-base` +
  `extract_reserve_mcp` helper.
- "Reserve MCP represents the marginal cost of providing one additional MW
  of reserve capacity system-wide" → **Mapped** into the
  `extract-reserve-mcp-base` step description.
- Binding-lines section: `BINDING_THRESHOLD = 99.0`, `b = 1.0 / x`,
  `flow_MW = b * (theta.value[f] - theta.value[t]) * baseMVA`,
  `loading_pct = abs(flow_MW) / rate * 100`, the `x != 0 and rate > 0`
  guard → **Mapped** into `find_binding_lines` (with `DEFAULT_BINDING_THRESHOLD_PCT`
  exposed as the module constant) and the `find-binding-lines-base` step.
- Reference to the `dc-power-flow` skill ("See the dc-power-flow skill for
  line-flow calculation details") → **Deliberate drop** of the
  cross-skill pointer. The helper now self-contains the small flow formula
  needed for binding-line detection; agents that need full DC-power-flow
  machinery still load that sibling skill independently.
- "Counterfactual Analysis" four-step recipe (solve base, modify
  constraint, solve CF, compute impact) → **Mapped** to the
  step sequence `solve-base-case` → `modify-line-for-counterfactual` →
  `solve-counterfactual-and-extract` → `compute-impact` → `assemble-report`.
- Modify-line code block including the bidirectional `or (br_from ==
  target_to and br_to == target_from)` match and `branches[k, 5] *= 1.20`
  → **Mapped** into `modify_line_limit` (with `scale_factor` parameterized
  rather than hard-coded to 1.20; the 1.20 value lives in the first
  scenario where the task specifies it).
- "Cost reduction = base_cost - cf_cost. Should be >= 0." → **Mapped** to
  `compute_impact` with a small clamp on solver-noise-level negatives and
  a comment that meaningfully negative values are left visible.
- "Delta = cf_lmp_map[bus] - base_lmp_map[bus]; negative = price decreased"
  → **Mapped** into `compute_impact` (sorted by delta ascending, then bus
  for determinism).
- "congestion_relieved if line was binding in base but not in CF" →
  **Mapped** into `compute_impact` using `_is_target_line` (bidirectional
  match).
- "Economic Intuition" bullets ("relaxing a binding constraint cannot
  increase cost", "cost reduction quantifies the shadow price of the
  constraint", "LMP convergence after relieving congestion") → **Mapped**:
  the first bullet is enforced by `compute_impact`'s clamp + comment; the
  other two are surfaced in `purpose` and in the first scenario's outcome.
- The `top_n = 3` value in the task's `report.json` schema (`buses_with_largest_lmp_drop`
  has three entries) → **Mapped**: surfaced as the default `top_n=3` in
  `compute_impact` and the `compute-impact` step description.

## On `do_not_use_when`

The original skill does not call out non-applicability. Three were added:
AC-OPF (different dual semantics, different per-unit conventions), models
without explicit per-bus balance constraints (LMPs not separable), and the
"no solved problem object" case (the helpers read `dual_value` directly).
These calibrations help the agent pick a different tool when the
DC-OPF-with-named-balance-constraints assumption fails.

## Schema validator note

`scripts/validate.py` in the bundled `aip` skill resolves the schema by
matching `metadata.aip.schemaId` against the `$id` of any `*.schema.json`
under `source/`. The procedure schema is copied verbatim from
`.claude/skills/aip/assets/aip-schemas/procedure.schema.json`; its `$id`
is already the canonical `v0.3a2` URL, so no further wiring is required.
