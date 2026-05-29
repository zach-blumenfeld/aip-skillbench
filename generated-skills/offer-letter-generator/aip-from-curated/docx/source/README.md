# Conversion notes: curated `docx` skill → AIP procedure

## Source

Original Agent Skill from `vendor/skillsbench/tasks/offer-letter-generator/environment/skills/docx/SKILL.md` (kept verbatim alongside this file as `SKILL.md`).

## Schema choice

Used the bundled `procedure.schema.json` (AIP v0.3a2). The source skill is structured as a runbook for filling Word templates — a procedure with steps, gotchas, and concrete code patterns. No new schema was needed.

## Mapping

Each piece of source content was classified against the AIP compilation rule (mapped / schema gap / body drop / deliberate drop).

| Source content                                                               | Disposition                                              |
|------------------------------------------------------------------------------|----------------------------------------------------------|
| "Split placeholder problem" explanation                                      | Mapped — encoded as anti-pattern + reason the fill script works at paragraph level. |
| Naive run-level replacement anti-example                                     | Mapped — anti-pattern.                                   |
| "Paragraph-level search and rebuild" code                                    | Mapped — implemented inside `scripts/fill_template.py`.  |
| "Regex-based full replacement" code                                          | Mapped — implemented inside `scripts/fill_template.py`.  |
| Headers/footers section + code                                               | Mapped — `fill_template.py` walks `section.header/footer.paragraphs`. |
| Nested tables section + code                                                 | Mapped — `fill_template.py` recurses through `cell.tables`. |
| Conditional `{{IF_X}}...{{END_IF_X}}` section + code                         | Mapped + extended — `fill_template.py` handles both same-paragraph and cross-paragraph IF/END_IF pairs, while the source only handled the same-paragraph case. |
| "Complete solution pattern" end-to-end script                                | Mapped — that script is essentially `scripts/fill_template.py`. |
| Common pitfalls list                                                         | Mapped — anti-patterns.                                  |

## Steps shape

Three steps, all script-backed:

1. **inspect-template** — `scripts/list_placeholders.py` lists every distinct `{{KEY}}` found across body, tables, headers, footers. Lets the agent diff against the supplied data and catch missing values up front.
2. **fill-template** — `scripts/fill_template.py` performs the placeholder substitution and conditional resolution. This is the heart of the procedure; all the run-splitting / nesting / header-footer / IF-block logic lives here.
3. **verify-output** — `scripts/verify_output.py` re-opens the saved `.docx` and asserts no `{{...}}` markers remain. Closes the validation loop.

## Frontmatter

`name: docx` is unchanged (the task's mounted skill name must match). `description` is preserved verbatim from the source skill. AIP metadata (`spec`, `schemaId`) added under `metadata.aip.*`.

## Truthy semantics for conditionals

The source's worked example assumed `data['RELOCATION_PACKAGE'] == 'Yes'`. The fill script generalises this: `True`, non-zero numbers, and `yes/y/true/t/1` (case-insensitive) are truthy; everything else (including missing keys) is falsy. This avoids regressing the obvious case while handling boolean/integer data.

## What was extended beyond the source

- Cross-paragraph `{{IF_X}}...{{END_IF_X}}` handling. The source's `handle_conditional` only worked when both markers sat in one paragraph. The fill script first resolves cross-paragraph pairs per container, then handles same-paragraph pairs in a second pass.
- A standalone `verify_output.py` validator. The source pattern saved and returned; the AIP version adds a self-check the agent can run before declaring success.
- A `list_placeholders.py` helper for the inspect step. Useful for diffing the template against the data file before filling.
