---
name: docx
description: Fill Word (.docx) templates whose placeholders use the {{KEY}} convention, robustly handling Word's split-run XML storage, nested tables, headers/footers, and {{IF_X}}...{{END_IF_X}} conditional blocks. Use when filling a .docx from a template plus a JSON data file, when python-docx replacements miss placeholders that are visible in the document, or when a template embeds conditional sections to evaluate against data.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires python3 with python-docx installed (`pip install python-docx`).
---

```yaml
purpose: >
  Fill Word (.docx) templates whose placeholders use the {{KEY}} convention.
  Encapsulates the four python-docx gotchas that break naive code: split
  placeholders (Word splits {{NAME}} across XML runs), nested tables,
  section headers/footers, and {{IF_X}}...{{END_IF_X}} conditional blocks.
  All of the deterministic XML/regex work lives in the backing script; the
  agent's job is to identify the inputs and decide which IF blocks to keep.

trigger_when:
  - User asks to fill or generate a .docx from a template containing {{PLACEHOLDER}} tokens.
  - python-docx replacement misses a placeholder that is visible in the rendered document (almost always a split-run issue).
  - The template contains {{IF_X}}...{{END_IF_X}} conditional sections to evaluate against a data field.
  - The template embeds nested tables, headers, or footers that also carry placeholders.

do_not_use_when:
  - Generating a Word document from scratch with no template.
  - The source is .doc (legacy binary), .rtf, PDF, HTML, or plain text.
  - Placeholders use a non-`{{KEY}}` syntax (Jinja `{{ key }}` with whitespace, `$VAR`, `<<KEY>>`, etc.). Adapt the regex in `scripts/fill_docx_template.py` or pick another tool.

scope_and_approval: >
  The skill writes a single output .docx at the path the agent supplies; it
  does not modify the input template or the input data file. No network
  access. No human approval required for normal runs.

steps:
  - name: collect-inputs
    description: >
      Identify the template path, data path, output path, and any explicit
      conditional overrides. The template is a .docx with {{KEY}} tokens;
      the data file is JSON whose top-level keys match those tokens.
      Read the user's instruction for any conditional rule it states
      explicitly (e.g., "keep the relocation block if RELOCATION_PACKAGE is
      Yes"). If the instruction states a rule that doesn't match the
      auto-resolution heuristic (see `fill-template`), pass it via
      `explicit_conditions`; otherwise omit and let the script auto-resolve.
    outputs:
      - name: template_path
        type: string
      - name: data_path
        type: string
      - name: output_path
        type: string
      - name: explicit_conditions
        type: object
        nullable: true
        description: >
          Optional map of IF tags to booleans, e.g. {"RELOCATION": true}.
          Tag is the part between IF_ and END_IF_, NOT the data field name.

  - name: fill-template
    description: >
      Run the deterministic fill. The script does paragraph-level placeholder
      replacement (correct under split runs), recurses through nested tables,
      walks each section's header and footer, and resolves
      {{IF_X}}...{{END_IF_X}} blocks using `explicit_conditions` when
      supplied, otherwise auto-resolves from the data: data[X] truthy, then
      data[X_PACKAGE] / data[X_ENABLED] / data[X_INCLUDED] truthy, otherwise
      default to KEEP. Truthiness treats "no"/"false"/"0"/"" (any case) as
      false; every other non-empty string is true.
    script: scripts/fill_docx_template.py
    inputs:
      - name: template_path
        type: string
      - name: data_path
        type: string
      - name: output_path
        type: string
      - name: explicit_conditions
        type: object
        nullable: true
    outputs:
      - name: output_path
        type: string
      - name: resolved_conditions
        type: object
        description: Map of IF tags to the boolean actually used. Inspect to confirm the auto-resolver matched the user's intent.

  - name: verify-no-placeholders
    description: >
      Re-open the saved output and scan body, tables (nested included),
      headers, and footers for surviving {{KEY}} tokens. Any leftover token
      means the fill missed a location — fix the script (or its inputs)
      rather than hand-editing the document.
    script: scripts/verify_no_placeholders.py
    inputs:
      - name: output_path
        type: string
    outputs:
      - name: ok
        type: boolean
      - name: remaining
        type: list[string]

scenarios:
  - need: >
      Fill `offer_letter_template.docx` from `employee_data.json`; keep the
      relocation block because RELOCATION_PACKAGE is "Yes".
    context: >
      The template has {{IF_RELOCATION}}...{{END_IF_RELOCATION}}. The data
      file has no top-level "RELOCATION" key but does have
      "RELOCATION_PACKAGE": "Yes".
    action: >
      Run `python3 scripts/fill_docx_template.py --template offer_letter_template.docx
      --data employee_data.json --output /root/offer_letter_filled.docx`.
      The auto-resolver finds no `RELOCATION` key, falls through to
      `RELOCATION_PACKAGE` = "Yes", and keeps the block while stripping the
      IF/END_IF markers.
    outcome: >
      `offer_letter_filled.docx` with every {{KEY}} substituted, the
      relocation paragraphs intact, no IF markers left behind, and the
      original run formatting preserved.

  - need: Force-strip an IF block even though data suggests keeping it.
    action: >
      Pass `--conditions '{"RELOCATION": false}'`. The explicit map wins
      over auto-resolution; the block and its markers are removed.
    outcome: Relocation paragraphs gone from the output.

  - need: A placeholder visible in Word ({{CANDIDATE_FULL_NAME}}) is never replaced by a naive script.
    context: >
      Inspection of the .docx XML shows it stored as two adjacent runs:
      `{{CANDI` and `DATE_NAME}}`. A `for run in para.runs: if "{{..." in run.text`
      loop never matches.
    action: >
      Use this skill's script. It reads `paragraph.text` (which concatenates
      runs), substitutes there, then writes the result into `runs[0]` and
      blanks the trailing runs.
    outcome: Placeholder replaced; the first run's formatting (font, bold, color) is preserved.

anti_patterns:
  - >
    Iterating run-by-run (`for run in para.runs: if "{{KEY}}" in run.text`).
    Misses split placeholders. Always operate at the paragraph level:
    compute `new_text` from `para.text`, then write it to `runs[0].text`
    and blank `runs[1:]`.
  - >
    Forgetting section headers and footers. They live on
    `doc.sections[i].header` and `.footer`, not in `doc.paragraphs` — a
    pass that only walks `doc.paragraphs` and `doc.tables` will leave
    placeholders there untouched.
  - >
    Forgetting nested tables. A pass over `doc.tables` does not descend
    into `cell.tables`. Recurse, or use the script in this skill.
  - >
    Leaving `{{IF_X}}` or `{{END_IF_X}}` markers in the output when the
    block is being kept. Strip the markers on the keep path as well as
    the drop path.
  - >
    Rebuilding a paragraph by deleting `runs[0]` and adding a fresh run.
    That drops the original run's font, bold, color, etc. Keep `runs[0]`,
    overwrite its `.text`, and blank the trailing runs.
  - >
    Hand-fixing surviving placeholders in the output file. They indicate a
    script bug (a region not walked, a regex too narrow, a missing key in
    the data) — fix the script so the next run is correct.
```
