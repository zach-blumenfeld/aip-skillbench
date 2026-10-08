# Source and provenance

`docx-template-fill` is compiled from one curated Agent Skill:

- `source/docx/SKILL.md` (copied verbatim) — "Word document manipulation with
  python-docx": the split-placeholder problem, the naive vs paragraph-level
  replacement, regex-based full replacement, headers/footers, nested tables,
  `{{IF_X}}...{{END_IF_X}}` conditional sections, a complete `fill_template` pattern,
  and five common pitfalls.

It was compiled against the task environment it will run in: a `ubuntu:24.04`
container with `python3` and `python-docx==1.1.2` only, holding
`/root/offer_letter_template.docx` (38,686 bytes) and `/root/employee_data.json`
(774 bytes, flat object of 22 string values). The real template was inspected:

- 21 distinct placeholders, 12 of them split across 2–6 runs, in the body, in tables
  nested inside a table (Basic Information / Compensation), in `header1.xml`
  (`Document ID: {{DOC_ID}}`) and `footer1.xml` (`Confidential - {{COMPANY_NAME}} ...`).
- One conditional block, `{{IF_RELOCATION}}...{{END_IF_RELOCATION}}`, inside a single
  paragraph, governed by data key `RELOCATION_PACKAGE: "Yes"` (the template has no
  `RELOCATION` key, so the condition-to-key mapping must be inferred).
- `Please respond by {{RESPONSE_DEADLINE}}.` — plain run followed by a placeholder
  split over three bold+underlined runs.
- Literal `$` precedes `{{BASE_SALARY}}`, `{{SIGNING_BONUS}}`, `{{RELOCATION_AMOUNT}}`;
  data values are `"185,000"` etc. (no symbol).

# Step-kind choices

| Step | Kind | Why |
|---|---|---|
| inspect | execution | Finding placeholders across all parts, counting split runs, mapping `IF_X` to its data flag (`X`, or the single yes/no-valued `X_*` key), and listing missing values are deterministic rules. |
| route-inspect | router | Branch on the script's `inspect_status` (`ready` / `needs_input`). |
| resolve-inputs | client_task | Supplying a missing value or settling an unreadable flag needs the task text and judgment (e.g. a key under another name); the output is free-form data, not a fixed label. |
| fill | execution | All document surgery (conditional removal, split-run splice, every part, save) is deterministic and fragile; done by code. |
| verify-output | execution | "No `{{`, no markers, every expected value present" is a fixed rule over the saved file. |
| route-verify | router | Branch on `verify_status` (`verified` / `failed`). |
| repair | client_task | Fixes for anything the script missed (field codes, charts, stray markers) need hands-on editing; loops back to verify. |

No `decision` step: every judgment the source calls for (does a block apply, is a
value present) has a deterministic answer from the data, so it is scripted; the only
non-deterministic cases (missing/ambiguous data) need generated values, so they go to
a client task.

# Deliberate improvements over the source code

- The source rebuilds a paragraph by writing all text into the first run, which drops
  formatting of later runs. Here the value is spliced into the run where the
  placeholder starts and the remainder is deleted from the following runs, so mixed
  formatting (the bold/underlined deadline) survives. The source's first-run pattern
  is kept in `references/python-docx-patterns.md` for hand repair.
- Parts are walked through the XML (`w:p` in document, all header*/footer*, footnotes,
  endnotes) instead of `doc.paragraphs` + `section.header/footer`, which also covers
  first-page/even headers, text boxes, and arbitrarily deep nested tables, and avoids
  python-docx creating a header part when touching a linked header.
- Placeholder regex widened from `[A-Z_]+` to `[A-Za-z0-9_]+` with optional inner
  spaces; conditionals spanning several paragraphs are supported in addition to the
  source's single-paragraph case.
- A duplicate currency symbol (template `$` + value `"$185,000"`) is stripped.
- Verification re-opens the saved file (source had none beyond pitfall #5).

# Completeness check (source -> skill)

| Source item | Where it lives |
|---|---|
| Split placeholder problem, why it happens | `scripts/docx_template.py` docstring + `splice`; anti_patterns[0]; reference §1 |
| Naive approach (fails) | reference §1 code; anti_patterns[0] |
| `replace_placeholder_robust` / paragraph-level rebuild | `splice` (improved); reference §2 |
| Regex full replacement over paragraphs, tables, nested tables, headers/footers | `apply_placeholders` + `text_parts`; reference §2–3 |
| Headers and footers via sections | `text_parts` (all header/footer parts); anti_patterns[1]; reference §3 |
| Nested tables, recursive `process_table` | XML walk reaches any depth; reference §3 code |
| Conditional sections: include strips markers and fills inside; exclude removes content | `apply_conditionals`; fill step order (conditionals before placeholders); reference §4 |
| Complete solution: load data JSON, load template, process all, `doc.save(output)` | inspect/fill steps; `load_data`; `fill_template.py` |
| Unknown keys left untouched (`if key in data`) | `apply_placeholders` leaves and reports them; inspect flags them as issues |
| Pitfall 1 forgetting headers/footers | anti_patterns[1]; verify-output checks all parts |
| Pitfall 2 missing nested tables | anti_patterns[1]; XML walk |
| Pitfall 3 split placeholders, work at paragraph level | anti_patterns[0]; `splice` |
| Pitfall 4 losing formatting, keep first run's formatting | anti_patterns[2]; splice keeps every run's formatting |
| Pitfall 5 conditional markers left behind | anti_patterns[3]; verify-output fails on any IF_/END_IF_ |

# Deliberate drops

- The source's `start_run = char_to_run[start_idx]` computation in
  `replace_placeholder_robust` is computed but never used; dropped as dead code.
- The source's `handle_conditional` only scans `doc.paragraphs` (not tables or
  headers); superseded by the all-parts implementation rather than copied as-is.
- The source sets an excluded single-paragraph block to `''`, leaving an empty
  paragraph; kept as-is (the "Relocation Assistance:" heading stays, as in the
  source), not a drop, noted here because it is visible in the output.
- The "Relocation Assistance:" heading sits outside the IF_RELOCATION markers in the
  real template. It is kept when the block is removed: only marked text is
  conditional, and deleting template text the author did not mark would be a guess.
  Recorded as an anti-pattern so agents do not "tidy" it away.

# Functional test log

- `aip run` on the real template + data: inspect -> fill -> verify -> end, `verified`;
  RELOCATION decided from `RELOCATION_PACKAGE: "Yes"`; deadline stays bold+underlined;
  `$` not doubled when a value already carries one.
- Gap data (`PTO_DAYS` missing, flag `"Pending"`): pause at resolve-inputs ->
  incomplete answer -> verify `failed` -> repair -> re-fill -> `verified`. Every
  router branch reached.
- Synthetic template: first-page + default headers, a 3-paragraph IF block set to
  false, a doubly nested table, a missing key -> flagged, then filled and verified.
- Two fresh agent sessions (relocation Yes, and relocation No with
  `CANDIDATE_FULL_NAME` renamed) both ended `verified`. Fixes from their feedback:
  inspect now names likely alias keys for a missing placeholder; runs emptied by a
  splice are removed; fill clears the stale `inspect_status`/`issues`.
