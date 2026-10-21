# Filling Word templates with python-docx — repair guide

Load this when `fill_template.py` reported issues or the review found a defect and you
must fix the output `.docx` yourself.

## Rerun the script first (preferred fix)

`scripts/fill_template.py` also has a CLI. Run it from anywhere with the container's
`python3`; it rewrites the output from the template, so reruns are safe:

```bash
python3 scripts/fill_template.py --template /root/offer_letter_template.docx \
  --data /root/employee_data.json --output /root/offer_letter_filled.docx \
  --condition RELOCATION=yes          # force a {{IF_RELOCATION}} block on/off
  --map CANDIDATE_FULL_NAME=full_name # placeholder name -> data key when they differ
  --record 0                          # pick one record when the data holds several hires
```

`--condition`, `--map`, `--record` are repeatable/optional. It prints the same JSON report
(`issues` empty and `status: complete` means done).

Decide flag values from the data, never by guessing: a conditional `{{IF_X}}` follows the
data field for X (`X`, `X_PACKAGE`, `INCLUDE_X`, `HAS_X`, ...). Yes-like (`Yes`, `true`,
`1`, `y`) keeps the block and strips only the markers; no-like (`No`, `false`, `0`, empty)
removes the markers and everything between them. If the data truly has no value for a
placeholder, do not invent one; report it.

## Critical: split placeholder problem

Word often splits placeholder text across several XML runs (spell-check, formatting
edits, Word's internal structure). `{{CANDIDATE_NAME}}` may be stored as run 1
`{{CANDI` + run 2 `DATE_NAME}}`. So:

- **Never** search run by run (`if '{{NAME}}' in run.text`) — it misses split placeholders.
- Search at **paragraph level** (`paragraph.text` joins the runs), with the regex
  `\{\{([A-Z_]+)\}\}`, then rewrite the runs.
- Rebuilding the paragraph by putting the whole new text into the first run and blanking
  the others works but takes the first run's formatting for the whole paragraph. Better:
  rewrite only the characters of the placeholder (the script does this) so surrounding
  bold/underline survives.

Minimal robust replace (paragraph-level, keeps the first run's formatting):

```python
import re
def replace_in_para(para, data):
    text = para.text
    new = text
    for m in re.finditer(r'\{\{([A-Z_]+)\}\}', text):
        if m.group(1) in data:
            new = new.replace(m.group(0), str(data[m.group(1)]))
    if new != text and para.runs:
        para.runs[0].text = new
        for run in para.runs[1:]:
            run.text = ''
```

## Where the text lives — cover all of it

- Body paragraphs: `doc.paragraphs`.
- Tables, **including nested tables** — recurse into `cell.tables`:

  ```python
  def process_table(table, data):
      for row in table.rows:
          for cell in row.cells:
              for para in cell.paragraphs:
                  replace_in_para(para, data)
              for nested in cell.tables:
                  process_table(nested, data)
  ```

- **Headers and footers** are separate from the body, reached through sections:
  `for section in doc.sections: section.header.paragraphs / section.footer.paragraphs`
  (also `first_page_header`, `even_page_header` and the footer equivalents when used).
  Typical content: `Document ID: {{DOC_ID}}`, `Confidential - {{COMPANY_NAME}}`.

## Conditional sections `{{IF_X}}...{{END_IF_X}}`

- Both markers in one paragraph: keep → remove just the two markers (and fill any
  placeholders inside); drop → remove the markers and all text between them, and delete
  the paragraph if it is left empty.
- Markers in different paragraphs: drop → remove everything from the start marker to the
  end marker, including whole paragraphs/tables in between.
- Never leave `{{IF_...}}` / `{{END_IF_...}}` markers in the final document.
- Text outside the markers (e.g. a "Relocation Assistance:" heading) belongs to the
  template; leave it.

## Common pitfalls

1. Forgetting headers/footers — they are not in `doc.paragraphs`.
2. Missing nested tables — must recurse into `cell.tables`.
3. Split placeholders — always work at paragraph level, not run level.
4. Losing formatting — keep the first run's formatting when rebuilding (or splice only
   the placeholder characters).
5. Conditional markers left behind — remove `{{IF_...}}` markers after processing.
6. Double currency signs — the template writes `${{BASE_SALARY}}`; a value `"$185,000"`
   must lose its `$` or the letter reads `$$185,000`.

## Verify

Re-open the saved file and scan body, tables, headers and footers for any remaining
`{{` or `}}`; read the letter text once for obviously wrong values.
