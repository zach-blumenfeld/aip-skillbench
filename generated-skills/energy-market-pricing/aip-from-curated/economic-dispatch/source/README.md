# Source Notes — economic-dispatch (AIP conversion)

## Inputs

- `SKILL.md` — the original curated Anthropic-style Agent Skill for economic dispatch.
- `procedure.schema.json` — the AIP `procedure` schema this skill validates against.
- `references/cost-functions.md` (one level up at the skill root) — MATPOWER cost-function reference, preserved verbatim for progressive disclosure.

## Schema choice

Procedure. The original SKILL is an execution graph: parse MATPOWER arrays → build the convex objective → assemble constraints (limits, power balance, optional reserves) → solve → format dispatch outputs. That maps cleanly onto procedure steps with typed inputs/outputs. No need to draft a new schema.

## Script vs prose decisions

The original SKILL is dominated by deterministic, mechanical logic:
- Fixed MATPOWER column indices (`gens[:, 8]`, `gens[:, 9]`, `gencost[:, 3]`).
- Branching on `NCOST` (1 / 2 / 3) — a finite lookup over structured input.
- Per-unit conversion (`MW / baseMVA`).
- Constraint assembly and `cp.Problem(...).solve(solver=cp.CLARABEL)`.
- Output rounding and dictionary shape.

All of that goes into a single script: `scripts/economic_dispatch.py`. One file is enough — the cost builder, the reserve toggle, and the output formatter are not independently reusable.

Prose steps remain for the parts that require judgment:
- Deciding whether reserve co-optimization is in scope (depends on whether the problem statement / `network.json` carries `reserve_capacity` and `reserve_requirement`).
- Choosing whether power balance is sufficient or whether the agent must compose with `dc-power-flow` for line limits. The original SKILL flags this explicitly; we preserve it as guidance.
- Interpreting the solver status and reporting back to the user.

## Content classification (source → AIP body)

- **Mapped:** generator indices, cost-function format, optimization formulation, power balance, reserve co-optimization, operating margin, dispatch output format, totals calculation, solver selection — all consolidated into `scripts/economic_dispatch.py` and surfaced in the body as steps + anti-patterns + scenarios.
- **Body drop → fixed:** the original quadratic example "[2, 0, 0, 3, 0.01, 20, 100]" lives in `references/cost-functions.md` (verbatim copy).
- **Deliberate drop:** none. Every numeric rule, column index, and code fragment from the source either ended up in the script or in a reference file.

## Compatibility

- Python 3.10+
- `cvxpy` with the `CLARABEL` solver (default in recent CVXPY releases)
- `numpy`

## Not in scope (deliberately)

- Unit commitment (binary on/off decisions, startup/shutdown costs).
- Line flow / branch limit enforcement — that is the `dc-power-flow` skill's job; this skill calls power balance only.
- AC-OPF — voltages, reactive power, line losses are out of scope.
