# AIP conversion notes — `xlsx`

Source: `vendor/skillsbench/tasks/powerlifting-coef-calc/environment/skills/xlsx/SKILL.md` (Anthropic curated skill).

Schema: `procedure.schema.json` (bundled in this directory). The procedure schema fits because the source is a workflow over an execution graph — read/transform/write/recalc/verify — with library-choice branching and an explicit validation loop. No new schema warranted.

## Layout decisions

- `scripts/recalc.py` — copied verbatim from the original (originally at the skill root). Moved under `scripts/` so the procedure's `recalc` step can use the schema's `script:` field, which is documented as a path under `scripts/`. The body invocation was updated from `python recalc.py` to `python scripts/recalc.py` to match.
- `LICENSE.txt` — copied verbatim.
- `references/financial-models.md` — color coding, number formatting, formula construction conventions, hardcode-documentation format. Moved out of the body because it's domain-specific and only loads when the task is a financial model.
- `references/openpyxl-patterns.md` — pandas + openpyxl create/edit/library-selection patterns. Moved out of the body to keep `SKILL.md` lean; the agent loads it when authoring Python that drives Excel.
- `references/formula-verification.md` — verification checklist, common pitfalls, recalc.py output interpretation. Loaded before declaring a workbook done.

## What stays in the body

- Hard contract: zero formula errors, preserve existing template conventions.
- Library choice (pandas vs openpyxl) as a one-liner in step descriptions; details in the reference.
- The execution graph: choose-tool → load/create → modify → save → recalc → verify (loop).
- The "use formulas, not hardcoded values" rule, called out as both a step instruction and an anti-pattern (high-leverage, repeated in the source for emphasis).

## Mapped vs dropped

Every distinct piece of source content is either captured in the body, captured in a reference, or noted here:

- **Mapped to body** — purpose, trigger_when, zero-error contract, preserve-template rule, library choice, workflow steps, formulas-not-hardcoded rule, anti-patterns.
- **Mapped to references/financial-models.md** — color coding, number formatting, formula construction (assumptions placement, error prevention list, hardcode documentation).
- **Mapped to references/openpyxl-patterns.md** — pandas snippet, openpyxl create snippet, openpyxl edit snippet, library selection notes, working-with-pandas tips, working-with-openpyxl gotchas, code style guidelines.
- **Mapped to references/formula-verification.md** — essential verification, common pitfalls, formula testing strategy, recalc.py JSON output spec, error type meanings.
- **Captured in steps[*].script** — `recalc.py` invocation.
- **Deliberate drop** — None. Every section of the source SKILL.md is reachable from the AIP body via the references.

## Notes on script vs prose choices

- `recalc-formulas` is script-backed (`scripts/recalc.py`) — deterministic, mechanical, returns structured JSON.
- `choose-library`, `load-or-create`, `modify`, `save`, `verify-and-fix` are prose steps — they hinge on interpreting the task (is it analysis vs construction? does the template already establish conventions? which cells does the user want changed?), which is the kind of judgment the source guidance explicitly leaves to the agent.
