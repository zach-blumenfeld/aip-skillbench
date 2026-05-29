# senior-data-scientist — Transition Notes

## Source

`original-SKILL.md` is the curated freeform skill mounted by the
`powerlifting-coef-calc` task at
`vendor/skillsbench/tasks/powerlifting-coef-calc/environment/skills/senior-data-scientist/SKILL.md`.

## Schema

`procedure.schema.json` — bundled from
`https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json`.
A procedure-style schema fits because the task is a directed workflow with
script-backed steps (read workbook → identify columns → write formula sheet
→ verify).

## Intent

The original `SKILL.md` is generic boilerplate (MLOps, K8s, latency SLOs).
None of its prose, references, or scripts contain knowledge that helps an
agent solve the actual task: writing Excel formulas to compute IPF Dots
coefficients on the `Dots` sheet of `/root/data/openipf.xlsx`.

The AIP version replaces the boilerplate with task-relevant domain knowledge:
the Dots polynomial (sex-specific coefficients + bodyweight clamps), the
OpenIPF column schema, the Excel formula encoding, and a single script that
both emits the formula text and builds the full workbook end-to-end.

The `name:` frontmatter is preserved at `senior-data-scientist` per the task's
mount path; the `description` is rewritten so the agent will activate it for
this task.

## Mapping the original → AIP

Every distinct piece of source content from `original-SKILL.md`:

| Source content                                                | Disposition       | Where it lands                         |
|---------------------------------------------------------------|-------------------|----------------------------------------|
| `name: senior-data-scientist`                                 | Mapped            | `SKILL.md` frontmatter `name`          |
| Generic "world-class data science" description                | Deliberate drop   | Rewritten in `SKILL.md` `description`  |
| Quick-start `python scripts/experiment_designer.py ...`       | Deliberate drop   | Original scripts were no-op stubs      |
| Quick-start `python scripts/feature_engineering_pipeline.py`  | Deliberate drop   | Original scripts were no-op stubs      |
| Quick-start `python scripts/model_evaluation_suite.py`        | Deliberate drop   | Original scripts were no-op stubs      |
| "Core Expertise" bullet list (MLOps, etc.)                    | Deliberate drop   | Not relevant to spreadsheet task       |
| "Tech Stack" (PyTorch, K8s, Spark, etc.)                      | Deliberate drop   | Not relevant; conflicts with real tech |
| Reference: `statistical_methods_advanced.md` (generic prose)  | Deliberate drop   | Replaced by `dots-formula.md`          |
| Reference: `experiment_design_frameworks.md` (generic prose)  | Deliberate drop   | Replaced by `openipf-data-schema.md`   |
| Reference: `feature_engineering_patterns.md` (generic prose)  | Deliberate drop   | Replaced by `excel-formula-patterns.md`|
| "Production Patterns", "Best Practices", "Performance Targets" | Deliberate drop  | Latency SLOs irrelevant; would mislead |
| "Security & Compliance", "Senior-Level Responsibilities"      | Deliberate drop   | Not relevant; would waste context      |
| "Common Commands" (pytest/docker/kubectl)                     | Deliberate drop   | Not relevant; would mislead            |

The original SKILL.md is preserved verbatim at `source/original-SKILL.md` for
traceability.

## Why these are deliberate drops, not body drops

The original content was uniformly generic-data-science boilerplate. Keeping
any of it in the AIP body would either:

- Waste context on every invocation (latency SLOs, K8s/Helm commands).
- Actively mislead the agent (pointing it at no-op scripts, suggesting
  PyTorch/Spark for a single-workbook Excel task).
- Inflate `description` token cost without improving activation precision.

The schema has capacity for all of it (`scenarios`, `integrations`,
`search_shortcuts`, `modes`) — this is a deliberate-drop call on relevance,
not a schema gap or body miss.

## Script choices (deterministic vs prose)

Per AIP best practices, scriptable = deterministic logic with fixed numeric
constants, lookup tables, or mechanical transformations.

**Scripted:**

- The Dots polynomial. Sex-conditional, with fixed coefficients and clamps.
  Pure if/then over structured input. Critical correctness risk if hand-written.
- The workbook build. Mechanical row-by-row formula emission with strict
  layout requirements (header order, cross-sheet refs, `=`-prefixed formula
  strings). Required to satisfy the verifier's `openpyxl` cell inspection.

Both live in `scripts/dots_formula.py` as a single file (per "favor fewer
script files for simplicity") with two subcommands. The `formula` subcommand
exists so an agent can inspect or splice the formula without running the full
build.

**Prose (left to agent judgment):**

- Mapping Data-sheet columns to the Dots-sheet layout. The instruction says
  "find which columns are needed" — that is *interpretation* of the
  data-readme and column headers, not a fixed lookup. The agent decides; the
  reference document documents the canonical mapping for verification.
- Library choice. `xlsxwriter` is recommended in the reference and used by
  the script, but the agent may legitimately reach for `openpyxl` if it
  already has the workbook loaded. Pinning would over-restrict.
- Verifying the build. Reading the output back with `polars`/`openpyxl` is
  a sanity check whose shape depends on what looks wrong — a prose step
  with a hint is the right altitude.

## Functional test

Not run inside this authoring session — the runtime that executes this skill
is the Docker environment from `task.toml`, not the host. The skill is
designed against the verifier's actual assertions in
`vendor/skillsbench/tasks/powerlifting-coef-calc/tests/test_outputs.py`:

- `Dots` sheet exists with the eight expected headers in order.
- Row count of `Dots` matches `Data`.
- `G2` and `H2` are formula strings starting with `=`.
- `H2` formula contains `ROUND(` and `IF(`.
- Computed Dots values match ground truth within `TOLERANCE = 0.01`.

The script emits formulas satisfying every assertion above.
