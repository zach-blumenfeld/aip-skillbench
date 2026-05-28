# xlsx — AIP conversion rationale

This is an AIP-formatted port of the curated Anthropic `xlsx` skill found at
`vendor/skillsbench/tasks/financial-modeling-qa/environment/skills/xlsx/`.
The source `SKILL.md` is bundled here as `original-SKILL.md` for traceability.

## Schema choice

`procedure.schema.json` (AIP `Procedure`). The source is a procedural
workflow — pick a tool, create/load, modify, save, recalculate, verify —
with a decision table for error types and explicit standards that act as
guardrails. Procedure fits naturally; no need to draft a new schema.

## Mapping notes

| Source section                              | AIP target                       |
|---------------------------------------------|----------------------------------|
| Description / when to use                   | `description` + `trigger_when`   |
| Zero formula errors mandate                 | `scope_and_approval`             |
| "Preserve existing templates" rule          | `scope_and_approval` + decision  |
| Color coding standards                      | `modes[financial-modeling-standards]` |
| Number formatting standards                 | `modes[financial-modeling-standards]` |
| Formula construction rules                  | `modes[financial-modeling-standards]` |
| Documentation for hardcodes                 | `modes[financial-modeling-standards]` |
| Reading & analyzing with pandas             | `modes[pandas-data-analysis]`    |
| Creating / editing Excel with openpyxl      | `modes[openpyxl-formulas-formatting]` |
| Common Workflow (choose / create / modify / save / recalc / verify) | `steps`            |
| `recalc.py` errors (#REF!, #DIV/0!, …)      | `decisions`                      |
| Formula Verification Checklist              | `modes[formula-verification-checklist]` |
| "Use Formulas, Not Hardcoded Values" rule   | `anti_patterns` + `scenarios`    |
| Best practices (library selection, pandas/openpyxl tips) | folded into respective `modes` |
| Code Style Guidelines                       | `anti_patterns`                  |

## Selective typing rationale

- `steps` are fully typed records — the agent loops over them in order and
  `recalculate`/`verify-and-fix` use `depends_on` to express that they
  follow `save`.
- `decisions` is a typed records table — the agent looks up by error
  signal, then applies the action.
- `modes` uses thin `{name, body}` envelopes because the bodies (pandas
  code, openpyxl code, financial-modeling standards, verification
  checklist) preserve their internal structure as prose, but each block
  needs a queryable name so the agent can jump to the right one.
- `trigger_when` and `anti_patterns` are flat string lists — plural,
  one-line items, nothing iterates by sub-field.

## Deliberate drops

None. All content from the source `SKILL.md` is mapped above. The verbatim
copies of `recalc.py` and `LICENSE.txt` live at the skill root, matching
the source layout, so the path `python recalc.py output.xlsx` keeps
working.
