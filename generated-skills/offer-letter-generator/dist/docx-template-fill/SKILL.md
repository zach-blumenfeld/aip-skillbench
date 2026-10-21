---
name: docx-template-fill
description: Fill a Word .docx template (offer letter, contract, form letter) from a JSON data file with python-docx. Replaces {{KEY}} placeholders even when Word has split them across runs, covers body, nested tables, headers and footers, and handles {{IF_X}}...{{END_IF_X}} conditional sections (keeps the content and strips the markers, or deletes the block) while keeping run formatting. Use when asked to fill, populate, or generate a document from a .docx template plus employee, candidate, or customer data.
compatibility: Python >= 3.8; pip package python-docx >= 1.1 (brings lxml). No other tools.
---

# DOCX Template Fill

## Trigger When

1. A task gives a `.docx` template with `{{PLACEHOLDER}}` fields and a JSON (or key/value) data file, and wants a filled `.docx` saved somewhere, e.g. "write an offer letter from `offer_letter_template.docx` and `employee_data.json`".
2. The template has conditional sections such as `{{IF_RELOCATION}}...{{END_IF_RELOCATION}}` that must be kept or removed based on a data field.
3. Any mail-merge-style generation of Word documents with python-docx, especially when a naive `run.text.replace` leaves placeholders unreplaced.

## Purpose

Produce a correctly filled Word document from a template and a data record, deterministically. The skill carries what an agent gets wrong unaided: Word splits `{{CANDIDATE_NAME}}` into runs like `{{CANDI` + `DATE_NAME}}`, so run-level replacement silently misses them; headers, footers and nested tables are not in `doc.paragraphs`; conditional markers must be removed even when the content is kept; and the condition flag is often named differently from the marker (`IF_RELOCATION` is governed by `RELOCATION_PACKAGE: "Yes"`). One script does inspection, filling and an independent verification.

## Procedure

Progress:
- [ ] 1. Preflight
- [ ] 2. Inspect template + data (`execution`)
- [ ] 3. Settle anything unresolved (`decision` / `client_task`)
- [ ] 4. Fill and verify (`execution`)
- [ ] 5. Read the result back (`decision`)

`TEMPLATE.docx`, `DATA.json`, `OUTPUT.docx` are the task's paths (usually template and data under `/root/`, output exactly where the task says, e.g. `/root/offer_letter_filled.docx`). The `scripts/fill_docx_template.py` path is relative to this skill's folder: run from there, or prefix it with the folder's absolute path.

### 1. Preflight

```bash
python3 -c "import sys, docx; assert sys.version_info >= (3, 8); print('ok')"
```

If it fails, name what is missing (Python 3.8+, `python-docx`). Install only if missing: `pip3 install python-docx` (add `--break-system-packages` on Debian/Ubuntu system Python).

### 2. Inspect (`execution`)

```bash
python3 scripts/fill_docx_template.py inspect TEMPLATE.docx --data DATA.json
```

Prints JSON: `placeholders` (each key joined across split runs, with count, parts such as `document.xml`/`header1.xml`/`footer1.xml`, and its data value), `conditionals` (each `IF_X` block, `include` true/false and the data key that `decided_by`), `data_keys_not_in_template`, and `problems`. Exit 0 = everything resolves, go to step 4. Exit 2 = `problems` lists what step 3 must settle. Add `--text` to dump every paragraph's text.

How the script decides a conditional `IF_X` (in order):
1. `--condition X=yes|no` from the command line.
2. A data key `X`, `IF_X`, `INCLUDE_X`, `HAS_X` or `SHOW_X` whose value is a yes/no word (case-insensitive) or a JSON boolean.
3. Exactly one data key containing `X` as a `_`-separated part (e.g. `RELOCATION_PACKAGE`) whose value is a yes/no word or boolean. Amounts and counts like `RELOCATION_AMOUNT: "15,000"` never count.
4. Key `X` holding the number 0 or 1.

Yes words: yes, y, true, on, include(d), eligible. No words: no, n, false, off, none, exclude(d), not eligible, ineligible, n/a, empty. If several keys match, or none, the condition is unresolved.

### 3. Settle unresolved items

Do this step only when inspect exits 2. Then re-run inspect with your answers until it exits 0.

**Decision: unresolved conditional.** Answer one per unresolved `IF_X`, from the data record and the task statement:

```yaml
include_block:
  type: noul
  instructions: >
    Should the content between {{IF_X}} and {{END_IF_X}} appear in the final document?
    Input: the block's text (from `inspect --text`), the candidate data keys named in
    `problems`, and the task statement.
  criteria:
    true: The task statement or a data field affirmatively grants what the block describes (e.g. the record says the person gets the package, or the task says to keep it).
    false: The data says no or is absent for the thing the block describes, or the governing field is blank.
```

Wrongly including an offer term the person was not granted is the costly mistake, so reconsider any close call that leans true. The task statement wins over a data field when they conflict (e.g. "keep it if RELOCATION_PACKAGE is Yes" names the field outright). Pass the answer as `--condition X=yes` or `--condition X=no`.

**Client task: missing placeholder value.** For a `{{KEY}}` with no data key, compose the value only from the data record: a differently named key with the same meaning (`NAME` vs `CANDIDATE_FULL_NAME`), or a combination (`FIRST_NAME` + `LAST_NAME`). Pass it as `--set KEY="value"`. Do not invent facts (salary, dates, names); if nothing in the data supports a value, say so in your final answer and leave the field out with `--set KEY=""` only when the task allows an incomplete document.

### 4. Fill and verify (`execution`)

```bash
python3 scripts/fill_docx_template.py fill TEMPLATE.docx --data DATA.json --out OUTPUT.docx [--condition X=yes|no]... [--set KEY=VALUE]...
```

What it does, in order, for every text part (body incl. nested tables and text boxes, all headers and footers incl. first-page/even, footnotes, endnotes):
1. Conditionals, innermost first. Include: delete only the `{{IF_X}}`/`{{END_IF_X}}` markers (a paragraph holding only a marker is removed). Exclude: delete everything from `{{IF_X}}` through `{{END_IF_X}}`, including whole paragraphs and tables between markers on different paragraphs; a paragraph left empty is removed (kept empty only where Word needs it: last paragraph of a table cell, or one carrying a section break). Text outside the markers, such as a "Relocation Assistance:" label, is never touched.
2. Placeholders `{{KEY}}` (spaces inside the braces allowed, key matched exactly, then case-insensitively) get the data value as written in the JSON: `"185,000"` stays `185,000`; booleans become Yes/No; null becomes empty. If the template already has `$` before the placeholder and the value starts with `$`, one `$` is dropped.
3. Each edit goes into the run where the match starts, so other runs keep their formatting (bold labels, a bold-underlined deadline).
4. Saves, reopens the file, and verifies: no `{{` or `}}` left anywhere, every inserted value is present in its part, kept blocks' text present, removed blocks' text gone.

Exit codes: 0 = saved and verified. 1 = saved but `verify.failures` lists problems: fix the cause (usually a marker syntax the script does not know, see below) and re-run. 2 = unresolved item, nothing saved: go back to step 3. 3 = template unreadable.

The JSON report lists every conditional (`include`, `decided_by`, `content`) and every replacement. Use it for your final answer.

If the template uses a different syntax (e.g. `[[KEY]]`, `{% if %}`, `{{#X}}...{{/X}}`), adapt the code in [references/python-docx-patterns.md](references/python-docx-patterns.md) rather than this script; read it then.

### 5. Read the result back (`decision`)

```bash
python3 scripts/fill_docx_template.py inspect OUTPUT.docx --text
```

```yaml
output_reads_correctly:
  type: noul
  instructions: Does every filled sentence in the dumped text read as a finished document for this record?
  criteria:
    true: Names, dates and amounts sit in the right places; currency signs are not doubled; no stray markers or empty sentence fragments; included or removed sections match the data.
    false: Any value is in the wrong slot, duplicated, missing, or a removed section left a dangling fragment inside a sentence.
```

If false, fix the input (`--set`, `--condition`) and re-run step 4. Do not edit the output by hand in ways that drop formatting.

## Gotchas

- Never replace at run level (`run.text.replace`); split placeholders are the norm in Word files, not the exception. The real offer-letter template splits about half of its 27 placeholder uses, e.g. `{{RESP` + `ONSE_DEAD` + `LINE}}`.
- `doc.paragraphs` skips headers, footers and table cells; `doc.tables` skips nested tables. The script walks every XML part instead.
- The conditional's flag name usually differs from the marker (`IF_RELOCATION` ← `RELOCATION_PACKAGE`). Keys sharing the prefix but holding amounts or counts (`RELOCATION_AMOUNT`, `RELOCATION_DAYS`) are values to insert, not flags.
- Keeping a block still means removing its `{{IF_...}}`/`{{END_IF_...}}` markers. Leftover markers are the most common failure.
- Keep values verbatim. Do not reformat numbers or dates; the template supplies `$`, "per year", "shares", "days".
- A flag key such as `RELOCATION_PACKAGE` may have no placeholder of its own; showing up in `data_keys_not_in_template` is normal.
- Write the output to exactly the path the task names; the script creates missing parent folders.
