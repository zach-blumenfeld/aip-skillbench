---
name: docx
description: Word document manipulation with python-docx - handling split placeholders, headers/footers, nested tables
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Fill `{{PLACEHOLDER}}` markers in a Word (.docx) template with values from a
  data file, robustly handling the edge cases that break naive run-level
  replacement: placeholders split across XML runs, content inside tables
  (including nested tables), text in section headers and footers, and
  `{{IF_X}}...{{END_IF_X}}` conditional blocks that should be kept or removed
  based on a data flag.

trigger_when:
  - User asks to fill a Word template, generate a Word document from a template, or perform a mail-merge into a .docx.
  - A task provides a `.docx` template with `{{KEY}}`-style placeholders plus a JSON or dict of values.
  - Naive `run.text.replace('{{KEY}}', value)` silently fails to substitute some placeholders.
  - Template contains `{{IF_X}}...{{END_IF_X}}` conditional blocks gated on a data flag.

do_not_use_when:
  - Source is `.doc` (legacy binary format) — convert to `.docx` first or use a different library.
  - Task needs rich Markdown/HTML-to-Word rendering — use docxtpl or a Jinja-based engine instead.
  - Task only reads text out of an existing .docx — this is a template-fill skill, not an extraction skill.

steps:
  - name: inspect-template
    description: List every distinct `{{KEY}}` found in the template (body, tables, headers, footers) so you can diff against the supplied data and catch missing values or typos before filling.
    script: scripts/list_placeholders.py
    inputs:
      - name: template-path
        type: string
        description: Path to the .docx template.
    outputs:
      - name: placeholders
        type: list[string]
        description: Distinct placeholder keys (without the surrounding `{{ }}`), one per line on stdout.

  - name: fill-template
    description: Substitute every placeholder at the paragraph level (to survive split runs), recurse through nested tables, process headers and footers, and resolve `{{IF_X}}...{{END_IF_X}}` conditional blocks against the data. Writes the filled document to `output-path`.
    script: scripts/fill_template.py
    depends_on:
      - inspect-template
    inputs:
      - name: template-path
        type: string
      - name: data-path
        type: string
        description: Path to a JSON file mapping placeholder keys to string values.
      - name: output-path
        type: string
        description: Where to write the filled .docx.
    outputs:
      - name: output-path
        type: string
        description: Echoed to stdout on success.

  - name: verify-output
    description: Re-open the saved .docx and assert no `{{...}}` markers remain anywhere (body, tables, headers, footers). Exit non-zero with the list of leftovers if the fill missed anything.
    script: scripts/verify_output.py
    depends_on:
      - fill-template
    inputs:
      - name: output-path
        type: string
    outputs:
      - name: leftover-placeholders
        type: list[string]
        description: Markers still present after fill. Empty list (and exit 0) means success.

anti_patterns:
  - Calling `run.text.replace('{{KEY}}', value)` directly. Word stores placeholders across multiple XML runs after spellcheck or formatting changes, so the literal `{{KEY}}` never appears in any single run and the replacement silently no-ops. Always work at the paragraph level — concatenate all run text, do the replacement on the joined string, and push the result back into the first run while clearing the rest.
  - Iterating only `doc.paragraphs`. Misses content in tables, nested tables (yes, `cell.tables` is real), section headers, and section footers. Visit all four explicitly.
  - Not recursing into `cell.tables`. Tables inside table cells are common in templated letters and contracts; a flat loop misses them.
  - Leaving `{{IF_X}}` and `{{END_IF_X}}` markers in the final document when the condition was true. Strip the markers, keep the content between them.
  - Dropping the conditional block when the condition was true (or keeping it when false). Resolve truthiness from the actual data value, not the marker's presence.
  - Trusting "the template looks fine." Word's XML run-splitting is invisible until the replacement silently no-ops. Always run the verify step before declaring success.

scenarios:
  - need: "Generate an offer letter from `offer_letter_template.docx` plus `employee_data.json` where `RELOCATION_PACKAGE` is `Yes`. Output to `/root/offer_letter_filled.docx`."
    action: "inspect-template → fill-template (`--template offer_letter_template.docx --data employee_data.json --output /root/offer_letter_filled.docx`) → verify-output."
    outcome: "A clean filled .docx. The relocation block is kept with `{{IF_RELOCATION}}` and `{{END_IF_RELOCATION}}` markers removed. Every `{{...}}` is gone."
  - need: "Same template but `RELOCATION_PACKAGE` is `No`."
    action: "fill-template removes the entire `{{IF_RELOCATION}}...{{END_IF_RELOCATION}}` block (markers and content), then substitutes remaining placeholders."
    outcome: "Filled letter with the relocation section absent and no stray markers."
  - need: "Template has `{{IF_BONUS}}` and `{{END_IF_BONUS}}` on different paragraphs, with several content paragraphs between them."
    action: "fill-template's first pass scopes the IF/END_IF span within the container, then either strips both markers (truthy) or blanks every paragraph in the span (falsy)."
    outcome: "Cross-paragraph conditionals resolve the same way as same-paragraph ones."
```
