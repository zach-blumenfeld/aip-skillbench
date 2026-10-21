# Source and provenance

- `docx/SKILL.md`: the curated `docx` skill ("Word document manipulation with python-docx: handling split placeholders, headers/footers, nested tables"), copied verbatim. It was the only file in the input skill set.
- Task context used for design and testing (not copied here): the offer-letter task statement (fill `offer_letter_template.docx` from `employee_data.json`, save to `/root/offer_letter_filled.docx`, keep the `{{IF_RELOCATION}}` block when `RELOCATION_PACKAGE` is Yes and strip the markers), and the task container (Ubuntu 24.04, Python 3.12, `python-docx==1.1.2` only).

What inspecting the real template showed and shaped the skill: 27 placeholder uses, about half split across runs (up to 3 runs, e.g. `{{RESP|ONSE_DEAD|LINE}}`); one outer table holding two nested tables; placeholders in the header (`DOC_ID`) and footer (`COMPANY_NAME`); a bold-underlined `{{RESPONSE_DEADLINE}}` run that the source's collapse-into-first-run approach would flatten; a conditional block on one paragraph spread over 4 runs, governed by `RELOCATION_PACKAGE`, a key with a different name from the marker.

# Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Preflight (Python + python-docx check) | execution (one-liner) | Deterministic. |
| Inspect template and data (`fill_docx_template.py inspect`) | execution | Finding placeholders across split runs, in nested tables/headers/footers, and mapping them to data keys is pure code. |
| Which data key governs `IF_X`, and is it yes or no | execution, falling back to a decision | The lookup order (override, exact/prefixed key, single `_X_` key with a yes/no word, 0/1 number) and the yes/no word lists are fixed rules, so they are scripted. Only when no key or several keys qualify does the agent answer the `include_block` noul, with costly-mistake guidance. |
| Missing placeholder value | client task | Composing a value from differently named fields needs reading the record; the script cannot know synonyms. Bounded: no invented facts. |
| Conditional keep/remove, placeholder replacement, `$` de-duplication, empty-paragraph cleanup | execution (`fill`) | Deterministic text edits; run-aware so formatting survives. |
| Verification (no leftover braces, values present, kept/removed block text) | execution (inside `fill`) | Fixed rules checked on the reopened file. |
| Final read-back | decision (`output_reads_correctly`) | Whether the document reads correctly is a judgment on generated output, with a yes/no answer. |

One script file with subcommands, because inspect, fill and verify share all the XML helpers.

# Deliberate drops and changes

- **Source's replacement code (collapse paragraph text into run 1)**: replaced in the script by run-aware splicing, because collapsing loses formatting of later runs (the source's own pitfall #4, "keep first run's formatting", only half-solves it). The source code is kept, corrected, in `references/python-docx-patterns.md` for adapting to other marker syntaxes.
- **Source's `replace_placeholder_robust` example**: its `char_to_run` / `start_run` computation is unused (dead code) and it then collapses the paragraph; superseded by `splice()`. Its idea (search joined paragraph text, rebuild runs) is kept.
- **Source's `handle_conditional` exclude branch** set the whole paragraph to `''`, which would also delete text outside the markers on that paragraph, and it handled only same-paragraph markers. The script deletes exactly the marked span and also handles markers on different paragraphs, nesting, and marker-only paragraphs.
- **Source's regex `[A-Z_]+`**: widened to letters, digits, `_`, `.`, `-` with optional spaces inside the braces, so `{{ name }}` or `{{ADDRESS_LINE2}}` are found.
- **Source's single-level nested-table loop** (in "Best Practice"): superseded by its own recursive `process_table`, and in the script by walking every `w:p` in every text part, which also covers text boxes, first-page/even headers, footnotes and endnotes.
- **"Usage" line** `fill_template('template.docx', 'data.json', 'output.docx')`: replaced by the script's CLI.
- Nothing else dropped: split placeholders, headers/footers, nested tables, conditional sections and all five pitfalls are in SKILL.md (Procedure + Gotchas) and the reference.
