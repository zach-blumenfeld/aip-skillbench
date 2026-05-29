# Conversion notes — `unit-commitment-operating-rules` (curated → AIP)

## Sources used

- `source/SKILL.md` — verbatim copy of the curated freeform skill from
  `vendor/skillsbench/tasks/energy-unit-commitment/environment/skills/unit-commitment-operating-rules/SKILL.md`.
- `source/procedure.schema.json` — bundled local copy of the AIP procedure
  schema (`v0.3a3`). The skill validates against this schema; the `$id` still
  points to the shared canonical URL.
- `vendor/skillsbench/tasks/energy-unit-commitment/tests/test_outputs.py` —
  the task grader. Read to extract the exact pglib-uc input shape, the
  required report schema, and the numerical tolerances used. The validator
  script mirrors these checks; the skill body mirrors the data shape.
- `vendor/skillsbench/tasks/energy-unit-commitment/instruction.md` — task
  prompt. Read to confirm output convention (actual MW, not above-min) and
  the JSON report schema the agent must produce.

## Schema choice — `procedure`

Reused the existing `procedure.schema.json` (no new schema drafted). UC
operating rules are an execution graph: parse → choose convention →
formulate → solve → extract → validate → finalize. The procedure schema's
`steps`/`inputs`/`outputs`/`anti_patterns`/`scenarios` cover everything the
source SKILL.md contains; nothing in the source needed a typed field the
schema lacks.

## Script vs prose split

One script: `scripts/validate_schedule.py`. Everything else is prose.

**Why a single mega-validator instead of one script per check.** The grader
runs every check together against one report. Splitting the validator into
per-constraint scripts would just push parsing logic into every file and
make the agent compose them. The skill best-practices doc explicitly
prefers fewer, cohesive scripts over micro-scripts.

**What the validator covers** (deterministic, mechanical, mirrors
`test_outputs.py`):

- Required summary keys, `solver_status` ∈ accepted set, `reported_mip_gap`
  shape, `time_periods` / generator counts match the case.
- Array shape, dtype, and binary tolerance for `commitment`, `startup`,
  `shutdown`.
- Startup/shutdown reconstructed from `commitment` and `unit_on_t0`; must
  match reported indicators; no simultaneous startup+shutdown.
- Must-run units always online.
- `pmin·u ≤ production ≤ pmax·u` and zero production+reserve when offline.
- Reserve deliverability with **startup** (`startup_reduction = max(pmax − ramp_startup_limit, 0)`) **and pre-shutdown** (`shutdown_reduction = max(pmax − ramp_shutdown_limit, 0)`) capacity reductions, against above-min variables.
- Ramping with reserve on the up side and initial `p0_above_min`.
- Minimum up/down: initial-condition obligation window (`min_up − time_up_t0`
  or `min_down − time_down_t0`) **and** in-horizon obligations after each
  startup/shutdown.
- Demand balance, system reserve requirement, renewable bounds, fixed
  renewables exactly tracked.
- Hourly summary fields reconstructed from arrays; `max_demand_balance_violation_MW`
  and `max_reserve_shortfall_MW` recomputed.
- `objective_cost` recomputed from piecewise breakpoints + startup tier lookup
  (largest lag ≤ prior offline duration). Compared to reported value within
  `max(TOL_COST_ABS, TOL_COST_REL · |cost|)`.

The verdict JSON includes both pass/fail per check and the recomputed
summary fields, so the agent writes the report's numeric fields from the
validator's output rather than its own bookkeeping. This is the single
biggest source of `cost_consistency` and `*_violation_MW` failures we saw
in the source skill's "common pitfalls."

### What was deliberately left as prose

- **Formulating the MILP.** Constraint families are model-design decisions —
  the agent reasons about variables, indexing, and solver API. Scripting the
  formulation would either box the agent into one library (scipy.milp,
  pyomo, gurobipy) or end up reimplementing whatever solver wrapper the
  curated `milp-solver-workflow` skill already provides.
- **Choosing actual-MW vs above-min variables internally.** Interpretive —
  depends on solver fluency and data layout. The skill states the rule
  (pick one, stay consistent) and the validator works on **actual MW**
  arrays from the final report.
- **Extracting the solver solution into report.json.** Format-specific,
  agent-judgment work; not a fixed transform.
- **Repairing failures.** Root-causing a violation is judgment — the
  validator points at *which* check failed and on which generator/hour, the
  agent decides whether the fix is a missing constraint, an extraction bug,
  or a tolerance issue.

## Completeness mapping (source → AIP)

Every section of the curated SKILL.md is captured:

| Curated section                       | AIP location                                                    |
|---------------------------------------|-----------------------------------------------------------------|
| Title + opening paragraph             | `purpose` + `trigger_when`                                      |
| UC in one paragraph                   | `purpose`                                                       |
| Keep these concepts separate          | `pick-output-convention` step description                       |
| Core feasibility checks (12-item list)| `validate-schedule` step + `validate_schedule.py` (full mirror) |
| Transition logic                      | `formulate-uc-model` description; validator recomputes          |
| Capacity and offline zeroes           | `formulate-uc-model` description; validator enforces            |
| Demand / renewables / system reserve  | `formulate-uc-model` description; validator enforces            |
| Reserve deliverability                | `formulate-uc-model` description; validator enforces startup+shutdown reductions |
| Ramping                               | `formulate-uc-model` description; validator enforces            |
| Minimum up/down                       | `formulate-uc-model` description; validator enforces            |
| Startup costs                         | `formulate-uc-model` description; validator implements lag→cost lookup |
| Production costs                      | `formulate-uc-model` description; validator implements piecewise interpolation |
| Implementation workflow (7 steps)     | `steps` array (parse → convention → formulate → solve → extract → validate → finalize) |
| Common pitfalls                       | `anti_patterns`                                                 |

## Compatibility note

The validator uses **numpy only**. The grader uses numpy + scipy (scipy
only for the benchmark MILP, which validation does not redo). If the
agent's runtime lacks numpy, the script will fail loudly — listed under
`compatibility`.

## Versions

- AIP spec: `v0.3a3` (matches the schema bundled in this folder)
- Source skill: copied 2026-05-28 from `vendor/skillsbench` HEAD
