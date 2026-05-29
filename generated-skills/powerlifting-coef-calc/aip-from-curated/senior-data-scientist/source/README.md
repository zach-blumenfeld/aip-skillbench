# Conversion Rationale — senior-data-scientist → AIP

Source: `vendor/skillsbench/tasks/powerlifting-coef-calc/environment/skills/senior-data-scientist/`

Target task type: compute the Dots coefficient for OpenPowerlifting / OpenIPF
competition data delivered as an Excel workbook with a populated "Data" sheet
and an empty "Dots" sheet, emitting Excel formulas (not precomputed values)
at 3-digit precision.

## Schema choice

`procedure.schema.json` (v0.3a2). The work is a deterministic execution graph:
inspect → select → build → verify, with each node script-backed and connected
by typed inputs/outputs. No alternative schema in `assets/aip-schemas/`
fits better.

## Source-content classification

Every distinct piece of content from the source SKILL.md and its
scripts/references was classified as **Mapped**, **Schema gap**, **Body
drop**, or **Deliberate drop**.

### Mapped

| Source                                                                       | Where in compiled body |
|------------------------------------------------------------------------------|------------------------|
| Source `description` ("statistical modeling, experimentation, …")            | Frontmatter `description` (carried over, plus task-specific keywords) |
| Source "Reference Documentation" pointers (3 references files)               | `search_shortcuts[0]` and reference files rewritten to actually carry the load-bearing content |
| Source "Quick Start" + scripts list (`experiment_designer.py`, etc.)         | Replaced by purpose-built scripts (inspect/select/build/verify); see "Replaced source files" below |
| OpenPowerlifting data dictionary (`data-readme.md` in environment/)          | `references/openipf_data_columns.md` (summarized to the columns the skill actually uses) |
| Dots polynomial constants + clamp ranges (from `solution/solve.sh`)          | `references/dots_formula.md` and embedded into `scripts/build_dots_workbook.py` |
| Excel-formula construction pattern (from `solution/solve.sh`)                | `references/excel_formula_patterns.md` and embedded into `scripts/build_dots_workbook.py` |
| Task instruction's 3-step workflow                                           | `steps[]` graph (inspect-workbook → select-dots-columns → build-dots-sheet → verify-output) |
| 3-digit precision requirement                                                | `purpose`, `anti_patterns`, and `ROUND(...,3)` in the build script |
| "Keep order and names of columns the same"                                   | `anti_patterns` entry and verified by `verify_output.py` |

### Schema gap

None. `procedure.schema.json` covered every piece of content that survived
classification.

### Body drop

None — no schema-supported content was dropped during compilation.

### Deliberate drop

The source SKILL.md is generic boilerplate auto-generated for a "senior data
scientist" persona; most of it is decorative. The following sections were
removed because they carry no task-specific load:

- "Core Expertise" bullet list (Advanced production patterns, MLOps, …) —
  generic; the actual expertise is the Dots formula and Excel-formula
  construction, captured in the body and references.
- "Tech Stack" matrix (PyTorch, Spark, LangChain, Kafka, …) — none of these
  tools apply to the spreadsheet workflow. The scripts pin polars +
  fastexcel + xlsxwriter, which is the actual stack.
- "Production Patterns" (Scalable Data Processing, ML Model Deployment,
  Real-Time Inference) — irrelevant to a one-shot spreadsheet task.
- "Best Practices" (TDD, code review, mentoring) — process advice unrelated
  to the procedure.
- "Performance Targets" (P50/P95/P99 latency, throughput, uptime) —
  irrelevant to writing an Excel file.
- "Security & Compliance" (PII, GDPR, …) — irrelevant; the input is public
  competition data.
- "Common Commands" (pytest, black, docker, kubectl, helm) — none used.
- "Senior-Level Responsibilities" (Technical Leadership, Strategic Thinking,
  Innovation, Production Excellence) — persona framing without procedural
  content.

The source `references/statistical_methods_advanced.md`,
`references/experiment_design_frameworks.md`, and
`references/feature_engineering_patterns.md` are nearly identical
boilerplate placeholders ("Production-First Design", "Pattern 1: Distributed
Processing", …) and were replaced wholesale with task-relevant references
documenting Dots, the OpenIPF column dictionary, and Excel formula patterns.

### Replaced source files

The source `scripts/experiment_designer.py`,
`scripts/feature_engineering_pipeline.py`, and
`scripts/model_evaluation_suite.py` are skeleton stubs whose bodies are
identical except for class names; the `_execute` method returns
`{"success": True}` without doing any real work. They were not copied
forward. The compiled skill has four purpose-built scripts that actually
carry the workflow:

- `scripts/inspect_workbook.py`
- `scripts/select_dots_columns.py`
- `scripts/build_dots_workbook.py`
- `scripts/verify_output.py`

## Why the skill name stayed `senior-data-scientist`

The benchmark mounts this skill by directory name. Renaming would break the
mount. The description is broadened to surface Dots / powerlifting / Excel
formula keywords so the agent activates appropriately.

## Files in this `source/` directory

- `SKILL.md` — verbatim copy of the source SKILL.md
- `procedure.schema.json` — bundled AIP schema
- `instruction.md` — task instruction (mounted at `/root/instruction.md` in
  the eval env)
- `data-readme.md` — OpenPowerlifting Data-sheet column dictionary
- `reference_solve.sh` — the task's reference solution; the Dots polynomial,
  clamp ranges, and Excel-formula structure used in `scripts/` are taken
  from this file
- `README.md` — this document
