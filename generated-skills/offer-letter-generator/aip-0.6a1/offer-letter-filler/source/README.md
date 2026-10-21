# offer-letter-filler — source and provenance

## Provenance

| File | Origin | Notes |
|---|---|---|
| `docx/SKILL.md` | `inputs/skills/docx/SKILL.md`, copied verbatim | The only curated skill: python-docx template manipulation (split placeholders, headers/footers, nested tables, conditional sections). |
| `task-instruction.md` | `inputs/instruction.md`, copied verbatim | The downstream task statement: fill `/root/offer_letter_template.docx` from `/root/employee_data.json`, save `/root/offer_letter_filled.docx`, keep the `{{IF_RELOCATION}}` block only when `RELOCATION_PACKAGE` is Yes and always remove the markers. |

The task's container (Ubuntu 24.04, `python3` 3.12, `python-docx==1.1.2`) shaped the
`requires` block: `python >= 3.10`, package `python-docx` (lxml comes with it).

Facts checked on the real template (they drove the script design): placeholders are split
across runs with differing formatting (`{{COMP`+`ANY_NAME}}` bold vs bold-italic,
`{{RESP`+`ONSE_DEAD`+`LINE}}` bold-underlined next to plain "Please respond by "); the
compensation and basic-info fields sit in tables nested inside a table; `{{DOC_ID}}` is in
the header and `{{COMPANY_NAME}}` in the footer; the relocation conditional is one
paragraph of four runs; currency signs live in the template (`${{BASE_SALARY}}`).

## Intent

One skill that turns any `{{KEY}}` .docx template plus a JSON data file into a finished
document, with conditionals resolved from the data, and that proves the result clean.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `fill-template` | execution | Every rule in the source is deterministic: paragraph-level regex matching, recursion through tables/headers/footers, conditional keep/remove by a yes/no flag, marker removal, leftover scan. Code is faster and more reliable than an agent re-implementing it. One script (fewer files). It also exposes a CLI so the repair step can rerun it with overrides. |
| `review-letter` | decision (noul `ready`, threshold 0.2) | Whether the result is a finished letter is a yes/no judgment over the script's report and the rendered text (catches broken values like `None` or `$$` that are not markup). Criteria spell out that template text outside markers is not a defect so the agent does not "fix" the template. |
| `by-readiness` | router | Branches on `ready`: true → end; false → repair. |
| `repair-letter` | client_task | Only reached when something needs judgment the script cannot make from the data alone (unclear flag such as "Maybe", data key named differently from the placeholder, several hires in one file). The agent reads the data and reruns the script with `--condition` / `--map` / `--record`, hand-editing only as a last resort. |
| `end` | end | Returns the output path, what was filled, and how each conditional resolved. |

## Improvements over the source code (deliberate)

- **Formatting**: the source rebuilds a paragraph by putting all text in the first run.
  On this template that would un-bold the date in "Please respond by **{{RESPONSE_DEADLINE}}**"
  and make "Please respond by" bold-underlined or not uniformly. The script instead splices
  only the placeholder's characters across the runs it spans (replacement inherits the
  first spanned run's formatting). The first-run rebuild is still documented in the
  reference as the simple fallback.
- **Coverage**: instead of walking `doc.paragraphs` + tables + `section.header/footer`
  (accessing a missing header through python-docx can create one), the script walks every
  `w:p` in the body (covers nested tables at any depth and text boxes) and in every
  header/footer part related to the document.
- **Conditionals**: the source only handles both markers in one paragraph and leaves an
  empty paragraph when removing. The script also handles blocks spanning paragraphs and
  tables, deletes paragraphs emptied by removal (keeping the one paragraph a table cell
  requires), maps `IF_X` to the data flag (`X`, `X_PACKAGE`, `INCLUDE_X`, `HAS_X`, …,
  e.g. `IF_RELOCATION` → `RELOCATION_PACKAGE`), and refuses to guess on unclear values
  (marks them unresolved and routes to repair).
- **Verification**: re-opens the saved file and scans every story for `{{`/`}}`;
  missing data values are left visible and reported, never invented.
- **Currency**: drops a value's leading `$`/`€`/`£` when the template already writes one.

## Completeness check (source line → where it lives)

| Source content (`docx/SKILL.md`) | Where |
|---|---|
| Split placeholder problem: Word splits `{{CANDIDATE_NAME}}` across runs due to spell-check/formatting/XML | `scripts/fill_template.py` (`ptext`, `splice`); reference "Critical: split placeholder problem"; anti_patterns[0] |
| Naive run-level approach fails | reference (Never search run by run); anti_patterns[0] |
| `replace_placeholder_robust` (char-to-run mapping, rebuild) | `splice` (char offsets → runs); reference |
| Regex-based full replacement `\{\{([A-Z_]+)\}\}`, only replace keys present in data | `PLACEHOLDER_RE` (also tolerates inner spaces/lowercase); missing keys left and reported; reference snippet |
| Process paragraphs, tables, nested tables, headers/footers | `stories()` + `root.iter(w:p)`; reference "Where the text lives"; fill-template description |
| Headers/Footers section (access via sections) | reference; script reads header/footer parts |
| Nested tables recursion `process_table` | covered by `iter(w:p)`; reference snippet |
| Conditional sections: keep → remove markers + fill inside; drop → remove content | `process_conditionals`; fill-template description; reference |
| Complete solution pattern (load JSON, load template, process, save) | `fill()`; CLI usage in reference |
| Pitfall 1 forgetting headers/footers | anti_patterns[1]; reference pitfalls |
| Pitfall 2 missing nested tables | anti_patterns[1]; reference pitfalls |
| Pitfall 3 split placeholders | anti_patterns[0]; reference pitfalls |
| Pitfall 4 losing formatting — keep first run's formatting | `splice` keeps formatting; reference pitfalls |
| Pitfall 5 conditional markers left behind | leftover scan in `reread`; review-letter criteria; anti_patterns[2] |
| Task: output path `/root/offer_letter_filled.docx` | start input `output_path` description; anti_patterns[4] |
| Task: keep relocation content if `RELOCATION_PACKAGE` is Yes, remove markers always | `condition_key` + `process_conditionals`; review-letter criteria |

## Deliberate-drop log

- Frontmatter `description` wording of the source skill — superseded by this skill's own description.
- The source's per-snippet "Usage" line (`fill_template('template.docx', 'data.json', 'output.docx')`) — replaced by the script's AIP stdin mode and CLI.
- The `handle_conditional(doc, condition_key, should_include, data)` signature — its behaviour is carried (and extended) by `process_conditionals`; the caller-supplied boolean is replaced by reading the flag from the data or `--condition`.
- Not dropped but bounded: removing a now-empty section heading above a removed block (e.g. "Relocation Assistance:") is NOT done — the task asks only to remove the conditional content and markers, and text outside markers belongs to the template.
