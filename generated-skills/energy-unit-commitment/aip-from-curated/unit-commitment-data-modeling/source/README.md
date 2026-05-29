# Source notes — unit-commitment-data-modeling → AIP

This folder bundles the canonical source used to author the AIP version
of `unit-commitment-data-modeling`:

- `original-SKILL.md` — verbatim copy of the curated source skill at
  `vendor/skillsbench/tasks/energy-unit-commitment/environment/skills/unit-commitment-data-modeling/SKILL.md`.
- `procedure.schema.json` — the AIP schema the AIP `SKILL.md` validates
  against (`procedure` family, v0.3a2). Bundled locally per AIP best
  practice so the skill is self-contained.

## Schema choice

`procedure` is the right fit. The source is a parsing workflow — load,
inspect, identify the time axis, identify resource sets, normalize,
preserve names/ordering, validate. That maps cleanly onto the
`procedure` schema's required `purpose` / `trigger_when` / `steps`
fields, with the conditional logic (startup-tier lookup, cost-curve
interpolation, parser validation) pushed into `scripts/`.

No new schema was authored.

## Logic encoded as scripts

The source guide contains three pieces of executable logic:

1. **Parser-level validation** — finite-value checks, length-vs-`T`
   checks, `pmin <= pmax`, `min <= max`, curve and tier minimum sizes,
   duplicate-ID checks, initial-state consistency, and warning on
   non-monotone tier lags. Per AIP guidance ("validation against a
   fixed set of rules" must be a script), this lives in
   `scripts/parser_checks.py` and returns a structured `{ok, errors,
   warnings}` report.
2. **Startup tier choice** — sort tiers by `lag`, pick the largest
   `lag <= prior_offline_duration`, fall back to the smallest-`lag`
   tier when the duration is below every threshold. Lives in
   `scripts/startup_tier.py`.
3. **Piecewise-linear total-cost interpolation** — sort breakpoints
   by `mw`, clamp at the endpoints, linearly interpolate between
   adjacent breakpoints. Lives in `scripts/cost_curve.py`.

The other source content — the concept-alias table, common data
shapes, the normalized `case` template, time/ordering/unit rules,
production-convention rules, and the renewables rules — is reference
material the agent consults while mapping source fields, not
executable logic. It lives in `references/parsing-patterns.md`,
loaded on demand from the body.

## Completeness audit (source → AIP)

Walked `original-SKILL.md` line by line. Classification:

- **Mapped** — parsing workflow (loading, inspection, time axis,
  resource sets, normalization, preservation of names and ordering,
  parser-level checks), concept-mapping table, common data shapes
  and the normalize template, time/ordering/units rules, production
  convention rules, startup-tier logic, cost-curve logic, renewables
  rules, and the common-mistakes list (→ `anti_patterns`).
- **Schema gap** — none. `procedure` covers every section.
- **Body drop** — none.
- **Deliberate drop** — none.

The detailed code snippets and the alias table moved into
`references/parsing-patterns.md` so the body stays under the AIP
budget; the body cites that reference at the point of use.
