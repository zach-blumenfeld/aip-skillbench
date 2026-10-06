# Task — answer a financial-model question

You are reasoning over an Excel workbook and a background PDF. Produce ONE grounded,
numeric-when-possible answer with a short justification trail.

## Question
{question}

## Workbook (extracted by `scripts/extract_sources.py`)
`xlsx_data` is a JSON object:
- `sheets.<name>.dims` — `[rows, cols]`
- `sheets.<name>.cells` — list of non-empty cells, each `{{ref, row, col, value, formula, number_format, comment}}`
  - `value` is the cached calculated value (may be `null` if the workbook was never opened in Excel/LibreOffice — if so, compute from `formula` and upstream inputs)
  - `formula` is the formula string (`"=SUM(...)"` ) or `null` for raw inputs
- `sheets.<name>.named_ranges` and `workbook_defined_names` — named refs
- `notes` — extractor warnings (empty values, broken refs); treat as context

```json
{xlsx_data}
```

## Background text (per-page plaintext from `pypdf`)
```
{pdf_text}
```

## How to answer

1. Restate the question in your own words to make sure you understood it. Note any
   ambiguity — if more than one answer could be defensible, pick the most literal reading
   and say what the alternative would be.
2. Locate the evidence:
   - For a cell lookup, name the sheet and ref (`Model!B14`).
   - For a derived metric, name the formula chain or the step-by-step calc.
   - For a narrative point, name the page (`background.pdf page 3`).
3. If the extracted material is missing what the question needs, say so explicitly rather
   than guessing — and name what you'd need (e.g. "cell `Assumptions!E7` is blank; the
   growth rate for 2027 is not in the model").
4. Load `references/xlsx-reading.md` if you need to reopen the workbook (table scan,
   formatting introspection, cross-sheet traversal beyond what `cells` carries).
5. Load `references/pdf-reading.md` if the PDF plaintext is garbled or you need table
   structure or metadata.
6. Load `references/financial-conventions.md` if the question hinges on units, color
   coding, formula conventions, or source documentation.
7. Preserve units and sign conventions from the model — don't convert `$mm` to raw
   dollars without saying so, and don't flip signs on costs.
8. Round only at the end, matching the source's precision.

## Return `inputs_to: end`
A JSON object merged into state:
```json
{{
  "answer": "<the direct answer, one line when possible>",
  "justification": "<2-6 bullet points citing cells / page refs>"
}}
```
Nothing else — the state already carries `question`.
