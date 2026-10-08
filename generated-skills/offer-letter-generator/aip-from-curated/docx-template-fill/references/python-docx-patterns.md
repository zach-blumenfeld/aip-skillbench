# python-docx patterns for hand repair

Load this only when the scripts could not finish the job (verify-output failed on
something a value change cannot fix). The scripts already implement all of this.

## Why run-level replacement fails

Word splits text across runs (spell-check, formatting edits, revision ids), so
`{{CANDIDATE_NAME}}` may be stored as run 1 `{{CANDI` + run 2 `DATE_NAME}}`.
Checking `'{{NAME}}' in run.text` misses it. Always search `paragraph.text` (the
concatenation of the runs).

```python
# DON'T: misses split placeholders
for para in doc.paragraphs:
    for run in para.runs:
        if '{{NAME}}' in run.text:
            run.text = run.text.replace('{{NAME}}', value)
```

## Paragraph-level replace that keeps formatting

Simplest fix (source pattern): write the rebuilt paragraph text into the first run
and blank the rest. It keeps only the first run's formatting, so use it only when the
paragraph is uniformly formatted:

```python
import re
PAT = re.compile(r'\{\{([A-Z0-9_]+)\}\}')
def replace_in_para(para, data):
    text = para.text
    new = PAT.sub(lambda m: str(data.get(m.group(1), m.group(0))), text)
    if new != text and para.runs:
        para.runs[0].text = new
        for r in para.runs[1:]:
            r.text = ''
```

When runs differ in formatting (e.g. `Please respond by ` plain + `{{RESPONSE_DEADLINE}}`
bold/underlined), splice instead: put the value in the run where the placeholder
starts and delete the placeholder's remaining characters from the following runs
(`scripts/docx_template.py: splice`).

## Where text lives (all must be covered)

- Body paragraphs: `doc.paragraphs` (top level only).
- Tables: `doc.tables` -> rows -> cells -> `cell.paragraphs`; recurse into
  `cell.tables` for nested tables.
- Headers/footers are NOT in `doc.paragraphs`: `section.header`, `section.footer`,
  plus `first_page_header/footer` and `even_page_header/footer` when enabled.
  Accessing a linked (`is_linked_to_previous`) header through python-docx can create
  a new header part; check the flag first.
- Text boxes, footnotes, endnotes: only reachable through the XML
  (`root.iter(qn('w:p'))` on each part).

```python
def process_table(table, data):
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                replace_in_para(para, data)
            for nested in cell.tables:
                process_table(nested, data)

for section in doc.sections:
    for para in section.header.paragraphs: replace_in_para(para, data)
    for para in section.footer.paragraphs: replace_in_para(para, data)
```

## Conditional blocks `{{IF_X}}...{{END_IF_X}}`

Include: delete only the two markers and fill placeholders inside. Exclude: delete
everything from `{{IF_X}}` through `{{END_IF_X}}`. Either way no marker may remain.

```python
def handle_conditional(para, key, include, data):
    s, e = '{{IF_' + key + '}}', '{{END_IF_' + key + '}}'
    text = para.text
    if s in text and e in text:
        if include:
            new = text.replace(s, '').replace(e, '')
            for k, v in data.items():
                new = new.replace('{{' + k + '}}', str(v))
        else:
            new = text[:text.index(s)] + text[text.index(e) + len(e):]
        if para.runs:
            para.runs[0].text = new
            for r in para.runs[1:]:
                r.text = ''
```

## Checklist before you finish

1. Headers/footers processed.
2. Nested tables recursed.
3. Split placeholders handled at paragraph level.
4. Formatting kept (first run, or splice for mixed runs).
5. No `{{IF_...}}` / `{{END_IF_...}}` markers left.
