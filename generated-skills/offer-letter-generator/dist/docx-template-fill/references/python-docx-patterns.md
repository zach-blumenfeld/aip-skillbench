# python-docx template patterns (for adapting to other placeholder syntaxes)

Read this only when `scripts/fill_docx_template.py` cannot be used as is, e.g. the
template uses `[[KEY]]`, `{% if %}`, or `{{#X}}...{{/X}}`. Prefer copying the script and
changing its `PH_RE` / `MARKER_RE` regexes: its run-aware `splice()` keeps formatting,
which the simpler code below does not.

## Split placeholder problem

Word stores `{{CANDIDATE_NAME}}` as several runs (`{{CANDI` + `DATE_NAME}}`) because of
spell-check, formatting changes, or its internal XML. This naive loop misses them:

```python
# DON'T DO THIS - won't find split placeholders
for para in doc.paragraphs:
    for run in para.runs:
        if '{{NAME}}' in run.text:  # Won't match if split!
            run.text = run.text.replace('{{NAME}}', value)
```

Always search `paragraph.text` (all runs joined), then rewrite the runs.

## Paragraph-level search and rebuild (simple, loses per-run formatting)

```python
import re

PATTERN = r'\{\{([A-Z_]+)\}\}'

def replace_in_para(para, data):
    text = para.text
    if not re.search(PATTERN, text):
        return
    new_text = text
    for m in re.finditer(PATTERN, text):
        if m.group(1) in data:
            new_text = new_text.replace(m.group(0), str(data[m.group(1)]))
    if new_text != text and para.runs:
        para.runs[0].text = new_text      # keep first run's formatting
        for run in para.runs[1:]:
            run.text = ''
```

Collapsing into run 1 drops formatting of later runs (a bold-underlined date becomes
plain). To keep it, put each replacement into the run where the match starts and trim
the matched characters from the following runs (what `splice()` in the script does).

## Walk every place text lives

```python
def process_table(table, data):
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                replace_in_para(para, data)
            for nested in cell.tables:          # tables can nest; recurse
                process_table(nested, data)

for para in doc.paragraphs:
    replace_in_para(para, data)
for table in doc.tables:
    process_table(table, data)
for section in doc.sections:                    # headers/footers are not in doc.paragraphs
    for hf in (section.header, section.footer,
               section.first_page_header, section.first_page_footer,
               section.even_page_header, section.even_page_footer):
        for para in hf.paragraphs:
            replace_in_para(para, data)
        for table in hf.tables:
            process_table(table, data)
```

Walking `part.element.iter(qn('w:p'))` over each header/footer part covers all of this
plus text boxes in one loop.

## Conditional sections `{{IF_X}}...{{END_IF_X}}`

```python
def handle_conditional(doc, key, include, data):
    start, end = '{{IF_' + key + '}}', '{{END_IF_' + key + '}}'
    for para in doc.paragraphs:
        text = para.text
        if start in text and end in text:
            if include:   # keep content, remove only the markers, fill placeholders inside
                new_text = text.replace(start, '').replace(end, '')
                for k, v in data.items():
                    new_text = new_text.replace('{{' + k + '}}', str(v))
            else:         # remove everything between (and including) the markers
                new_text = text[:text.index(start)] + text[text.index(end) + len(end):]
            if para.runs:
                para.runs[0].text = new_text
                for run in para.runs[1:]:
                    run.text = ''
```

This only handles markers in the same paragraph. When they sit on different paragraphs,
delete from the start marker to the end of its paragraph, every paragraph/table between,
and from the start of the end marker's paragraph through the marker; remove paragraphs
left empty, except the last paragraph of a table cell (Word requires one).

## Pitfalls

1. Forgetting headers/footers: they are not in `doc.paragraphs`.
2. Missing nested tables: recurse into `cell.tables`.
3. Split placeholders: always work at paragraph level, not run level.
4. Losing formatting: keep the formatting of the run that held the placeholder.
5. Conditional markers left behind: remove `{{IF_...}}` / `{{END_IF_...}}` after processing, also when the content is kept.
