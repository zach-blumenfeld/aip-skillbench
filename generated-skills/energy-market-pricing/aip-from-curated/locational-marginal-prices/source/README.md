# source/

Canonical source for the `locational-marginal-prices` AIP skill.

## Contents

- `procedure.schema.json` — the bundled AIP schema this skill validates against. Copied verbatim from `aip/assets/aip-schemas/procedure.schema.json` so the skill is self-contained.
- `original-SKILL.md` — the curated upstream skill from `vendor/skillsbench/tasks/energy-market-pricing/environment/skills/locational-marginal-prices/SKILL.md`, preserved as the canonical human-readable source.

## Mapping notes

The upstream skill is a how-to reference for extracting Locational Marginal Prices (LMPs) — and related dual-derived quantities — from a CVXPY DC-OPF solution. Mapping to the `procedure` schema:

- **Primary procedure (`steps`)**: the LMP extraction workflow (store balance constraint references → solve → read duals → scale per-unit duals to $/MWh).
- **`decisions`**: sign-convention semantics — positive vs negative LMPs and the diagnostic interpretation of each, plus the `None` dual case.
- **`scenarios`**: secondary dual-extraction use cases that share the same "store reference, solve, read dual" pattern but target different artifacts — reserve clearing price (system reserve constraint dual), binding-line identification (per-branch loading %), and counterfactual analysis (relax a limit, re-solve, compare costs/LMPs/congestion).
- **`anti_patterns`**: the failure modes the upstream skill implicitly warns against (forgetting to keep constraint refs, missing the per-unit → $/MWh scaling, treating negative LMPs as errors).

The `name` field is held fixed at `locational-marginal-prices` because the consuming SkillsBench task mounts the skill by that exact directory name.

No content from the upstream SKILL.md was dropped. The "Economic Intuition" tail on counterfactual analysis is folded into that scenario's `outcome` field.
