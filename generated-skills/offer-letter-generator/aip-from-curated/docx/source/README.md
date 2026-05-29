# Authoring notes — `docx` (AIP)

Curated source: `vendor/skillsbench/tasks/offer-letter-generator/environment/skills/docx/SKILL.md`.
The original is a python-docx tutorial. This AIP rewrite preserves the four techniques but compiles them into scripts so the agent invokes one deterministic pipeline instead of re-implementing snippets every run.

## Schema choice

`procedure.schema.json` (bundled). The skill is a procedure: collect inputs → fill template → verify. Conditional resolution is data-driven and so belongs inside a script (per the "script the deterministic parts" guidance), not in typed schema fields.

## Mapping — source content → compiled body

| Source content                                                                | Where it landed                                                                                              |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Split placeholder problem + paragraph-level rebuild (`replace_in_paragraph`) | `scripts/fill_docx_template.py` (`process_paragraph` + `rebuild_paragraph`); the *why* in `anti_patterns[0]` |
| `replace_all_placeholders` walking body + tables + headers/footers           | `scripts/fill_docx_template.py` (`fill` orchestration)                                                       |
| Nested tables — recurse into `cell.tables`                                    | `scripts/fill_docx_template.py` (`process_table`); `anti_patterns[2]`                                       |
| Headers/footers via `section.header` / `section.footer`                       | `scripts/fill_docx_template.py` (`fill`); `anti_patterns[1]`                                                 |
| `{{IF_X}}...{{END_IF_X}}` conditional sections (`handle_conditional`)         | `scripts/fill_docx_template.py` (`apply_inline_conditionals` + `strip_cross_paragraph_blocks`); `anti_patterns[3]` |
| "Complete Solution Pattern" full example                                      | `scripts/fill_docx_template.py` end-to-end (CLI-callable)                                                    |
| Common Pitfalls list                                                          | `anti_patterns` (all five)                                                                                   |
| Run-formatting preservation note                                              | `anti_patterns[4]`                                                                                           |

## Deliberate drops

- The raw Python tutorial snippets (each fenced ```` ```python ```` block in the source) are not duplicated as prose in the body — they exist as the implementation of `scripts/fill_docx_template.py`. Carrying both prose and code would waste body tokens and risk drift.

## Extensions beyond the source

The source pins `RELOCATION_PACKAGE == "Yes"` as the condition gate. To make the skill reusable across templates with other IF tags, the script:

1. Accepts an explicit `--conditions` JSON map (`{"TAG": bool}`) that overrides everything.
2. Auto-resolves each `IF_X` found in the document by checking, in order: `data[X]`, then `data[X + "_PACKAGE"]` / `_ENABLED` / `_INCLUDED`. Truthiness rule: `"no"/"false"/"0"/""` (any case) is false; every other non-empty string is true. Default: keep the block.

It also adds a cross-paragraph IF/END_IF pass (state machine over a paragraph list) because real templates often span the markers across paragraph breaks even if the offer-letter test happens not to. The original solve's single-paragraph approach still works as the first pass; the second pass only fires on markers that survived.

## Why these are script-backed, not prose

The fill logic is purely deterministic: regex matching, list iteration, fixed truthiness rules. Per AIP guidance, "deterministic if/then/else over structured inputs" → script. The remaining judgment call — *should the agent override auto-resolution because the user's instruction explicitly contradicts what the data implies?* — stays as the prose `collect-inputs` step, since it requires reading the user's wording.

## Validation

Run `uv run /Users/zach/dev/aip-skillbench/.claude/skills/aip/scripts/validate.py /Users/zach/dev/aip-skillbench/generated-skills/offer-letter-generator/aip-from-curated/docx` after any edit to `SKILL.md` or the bundled schema.
