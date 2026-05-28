# Source notes — xlsx (AIP conversion)

## Intent

Convert the curated Anthropic `xlsx` Agent Skill (in
`/home/zach_blumenfeld/aip-skillbench/vendor/skillsbench/tasks/protein-expression-analysis/environment/skills/xlsx/`)
into an AIP-format skill that validates against
`procedure.schema.json` (v0.3a2).

The original skill is a workflow: pick library → load/create → modify with formulas → save → recalculate → fix errors → verify. That maps cleanly onto the procedure schema: a graph of step nodes with one script-backed node (`recalc.py`).

## Source materials

- `SKILL.original.md` — verbatim copy of the upstream `SKILL.md`.
- `procedure.schema.json` — the AIP schema the body validates against.

## Mapping (source → AIP)

| Source section                              | Lands in                                                     |
|---------------------------------------------|--------------------------------------------------------------|
| Zero Formula Errors requirement             | `anti_patterns`, `verify-output` step, `verification-checklist.md` |
| Preserve Existing Templates                 | `study-existing-template` step, `openpyxl-patterns.md`, `anti_patterns` |
| Color Coding Standards                      | `references/financial-model-standards.md`                    |
| Number Formatting Standards                 | `references/financial-model-standards.md`                    |
| Formula Construction Rules                  | `references/financial-model-standards.md`                    |
| Documentation Requirements for Hardcodes    | `references/financial-model-standards.md`, `anti_patterns`   |
| Overview                                    | `purpose`                                                    |
| LibreOffice requirement                     | `compatibility`, `scope_and_approval`, `recalculate-formulas` step |
| Reading and analyzing data with pandas      | `references/pandas-patterns.md`                              |
| CRITICAL: Use Formulas Not Hardcoded Values | `write-data-and-formulas` step, `anti_patterns`, `openpyxl-patterns.md` |
| Common Workflow (6 steps)                   | The `steps` graph itself                                     |
| Creating new Excel files                    | `references/openpyxl-patterns.md`                            |
| Editing existing Excel files                | `references/openpyxl-patterns.md`                            |
| Recalculating formulas                      | `recalculate-formulas` step + `scripts/recalc.py`            |
| Formula Verification Checklist              | `references/verification-checklist.md`                       |
| Interpreting recalc.py Output               | `references/verification-checklist.md`                       |
| Best Practices (library selection)          | `search_shortcuts.Libraries`, `classify-task` step           |
| Working with openpyxl (`data_only` warning) | `references/openpyxl-patterns.md`, `anti_patterns`           |
| Working with pandas (dtypes, usecols)       | `references/pandas-patterns.md`                              |
| Code Style Guidelines                       | `references/code-style.md`                                   |

No source content was deliberately dropped. Every distinct rule, table, code block, and warning lands in either the body, a reference, or the recalc script.

## Why one script

The curated skill ships exactly one executable: `recalc.py`. It performs domain-specific logic (driving headless LibreOffice, scanning every cell for Excel errors, summarising) and is the load-bearing piece of automation. The remaining content is patterns the agent applies when authoring Python code with pandas/openpyxl — not standalone executables. Splitting those into stub scripts would add ceremony without adding determinism.
