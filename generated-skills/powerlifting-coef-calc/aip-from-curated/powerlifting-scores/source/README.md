# powerlifting-scores: provenance and compilation notes

## Provenance

Compiled 2026-10-08 from three curated Agent Skills, copied verbatim here:

| Folder | Origin | Role in this pack |
|---|---|---|
| `powerlifting/SKILL.md` | Curated skill "powerlifting": Dots, IPF GL, Wilks, Glossbrenner explanations plus OpenPowerlifting Rust implementations and tests | All scoring logic: `scripts/pl_lib.py`, `references/scoring-formulas.md` |
| `xlsx/SKILL.md`, `xlsx/recalc.py`, `xlsx/LICENSE.txt` | Anthropic xlsx skill (proprietary licence, see LICENSE.txt) | Output rules (formulas not values, zero errors, preserve template), LibreOffice recalculation; `scripts/recalc.py` is a verbatim copy; `references/xlsx-rules.md` |
| `senior-data-scientist/` (SKILL.md, 3 references, 3 scripts) | Curated skill "senior-data-scientist" | Almost nothing usable: see drop log |

Also consulted: the task environment's `data-readme.md` (OpenPowerlifting column definitions), condensed into `references/openpowerlifting-data.md`, and the sample workbook `openipf_cleaned.xlsx` (sheets `Data`: 20 lifters x 25 OpenPowerlifting columns with an Excel table `Frame0`, `Dots`: empty; no TotalKg column; numbers formatted `#,##0.000`; Place, WeightClassKg and Date stored as text). The manifest lists it at its real size (10,370 bytes), so it is complete, not truncated. The scripts are header-driven and make no assumption about row count, column positions, or sheet names beyond what the profile reports.

The Schwartz and Malone coefficients that Glossbrenner needs are imported in the source (`crate::schwartzmalone`) but not printed there. They were reconstructed from OpenPowerlifting's implementation and checked against the source's own Glossbrenner tests: men coef(100) = 0.5812707859533183, women coef(100) = 0.7152488066040259, points 581.27 and 492.53032, all reproduced exactly. The Schwartz piecewise tail above 126 kg is not covered by those tests. `references/scoring-formulas.md` says this too.

## Graph and step-kind choices

```
profile-workbook (execution) -> classify-request (decision) -> route-system (router)
  dots|wilks|ipf_gl|glossbrenner|multiple -> plan-layout (client_task) -> write-scores (execution) -> check-verification (router)
      pass|pass_cached -> final-check (client_task) -> end
      fail -> repair-plan (client_task) -> retry-or-stop (router): retry -> write-scores, stop -> final-check
  other -> manual-score (client_task) -> final-check
```

- **profile-workbook: execution.** Finding the data sheet, header positions, value sets (Sex/Event/Equipment), bodyweight range, and anomalies (negative lifts, blank bodyweight, DQ/DD/NS places, unknown sex) is deterministic. It also emits a header-matched draft plan, so the agent edits a plan instead of writing one from scratch.
- **classify-request: decision (choice).** Which system the task wants is a judgment over free text, but the answer space is fixed (`dots`, `wilks`, `ipf_gl`, `glossbrenner`, `multiple`, `other`). Threshold 0.7: picking the wrong system silently gives wrong numbers everywhere.
- **plan-layout: client_task.** Mapping the task's wording (sheet names, exact headers, column order, rounding, coefficient vs points, in-place vs new file) to a structured plan is generation that depends on prose. The plan's schema is fixed and the script validates it.
- **write-scores: execution.** All formula logic is code: constants, clamps, sex mapping (Mx -> men), IPF GL equipment/event lookup, zero rules, failed-lift totals, ROUND, cross-sheet references, header/format copying, plus caching values, LibreOffice recalculation, and cell-by-cell verification against the Python reference. One script, with shared logic in `pl_lib.py` (the profile reuses the header matching).
- **check-verification / retry-or-stop: routers** on script/agent-produced status values.
- **repair-plan: client_task.** Diagnosing a failed plan (wrong header, non-empty target) needs reasoning over the error report. The agent decides retry or stop, which bounds the loop.
- **manual-score: client_task.** For formulas the pack doesn't carry (Wilks2, old IPF points, Sinclair...) the agent must work by hand under the xlsx rules. The template forbids inventing coefficients.
- **final-check: client_task.** Checking that the output matches the literal task text and summarising it is judgment plus generation.

Design decisions:
- **Formulas, not values** (xlsx rule): copies are `=Data!A2`, totals and scores are Excel formulas with the constants inline. Coefficients are not moved into assumption cells. The task layout (an exact column list on a named sheet) overrides the financial-model convention, and extra cells could break graders that read the layout. Recorded in `references/xlsx-rules.md` and plan rule 5.
- **Cached values.** openpyxl writes formulas without results, and readers using `data_only=True` see `None` until a spreadsheet app recalculates. `write_scores.py` therefore (1) writes the Python reference results into the formula cells' cached `<v>` values, then (2) runs `recalc.py` (LibreOffice) when `soffice` exists, then (3) re-reads and compares every cell. `pass` = LibreOffice recalculated and matched; `pass_cached` = no LibreOffice, so the cached reference values stand. The workbook's `fullCalcOnLoad` flag makes Excel recalculate on open in either case.
- **IPF GL formula** uses an `INDEX({...},MATCH(key,{...},0))` lookup on event & sex & equipment-group (about 2.4k characters instead of 5.4k for nested IFs, safely under Excel's 8192 limit). Unknown combinations give 0, as in the Rust `_ => (0,0,0)` arm.
- **Failed lifts.** Default `failed_lift_policy: opl`: total = 0 when any lift is negative, following the data README ("TotalKg empty if a lift failed"). `sum` is available when a task wants a plain sum. On the sample data both give the same result (no negatives).
- **Sorting and ranking** (`sort_by`, `kind: rank`): added after a fresh-agent test where the task said "rank lifters by IPF GL". The row order is fixed at write time (each row's formulas point at a specific Data row); `RANK` cells stay live.
- **openpyxl bootstrap.** The container has openpyxl 3.1.5 (Dockerfile). Elsewhere `pl_lib.ensure_openpyxl()` re-runs the script once under `uv run --with openpyxl`.

Verification done while authoring: Python reference against every test in the source (Wilks coefficients/points, Glossbrenner coefficients/points/zero bodyweight, both IPF GL published examples: 112.85 and 96.78). Excel formulas were evaluated independently with the `formulas` package on a 30-row synthetic workbook (the real format plus edge rows: Mx, Single-ply/Multi-ply/Unlimited/Wraps/Straps, a bench-only and a deadlift-only entry, a negative squat, blank bodyweight, bodyweights 38.2, 160 and 215.5 kg). All four systems, 341 cells, matched the reference with 0 mismatches.

Functional tests (`aip run` + `aip resume`, inputs under `scratch/`): the Dots task on the real sample file and on the 30-row synthetic file (decision -> plan -> write -> pass_cached -> final-check -> end); Wilks + IPF GL `multiple` with a bad header (fail -> repair -> retry -> pass_cached -> end) and the same with `stop`; Wilks-2020 (`other` -> manual-score -> final-check -> end). The `pass` branch needs LibreOffice, which the authoring machine lacks and the task container has. Two fresh agents ran Dots and GL/Wilks tasks to `end` with no script errors. Their feedback led to sort/rank support, a warning that the draft's sheet-name guess may be wrong, and clearer column-default, partial-event-total and `multiple` wording. Authoring also caught a bug: an early failure omitted `output_path` and broke the stop path. It is fixed.

## Completeness walk (source -> pack)

powerlifting/SKILL.md
- DOTS intro/purpose (normalise totals across bodyweights; total + bodyweight inputs) -> `purpose`, `references/scoring-formulas.md` common rules.
- Garbled DOTS formula line and a..e explanation -> reference (with a note on the poly4 ordering); `pl_lib.DOTS`.
- Rust Dots constants, clamps 40-210 / 40-150, Mx -> men, zero bodyweight/total -> 0 -> `pl_lib.dots_coef`, `x_dots`, reference table, anti-pattern on clamps.
- Dots doc comment (BVDK, IPF Points not cross-sex, Tim Konertz) -> reference, one line.
- IPF GL calculator instructions (units, weight, gender, four lift types) -> reference lift-type mapping and kg note; plan rule 6 (pounds).
- IPC formula, A/B/C table, equipment collapse, dichotomous sex, SBD/B only, bw < 35, zero denominator, non-negative -> `pl_lib.IPF_GL`, `gl_params`, `points`, `x_ipf_gl`; reference.
- IPF GL tests -> reference; reproduced in authoring.
- Wilks equation, coefficient table, clamps and their rationale, tests -> `pl_lib.WILKS`, reference.
- Glossbrenner masters background, LT x GBC = PN, GPC usage -> reference. Piecewise Rust code -> `pl_lib.gloss_coef`, `x_gloss`. Tests -> reference.

xlsx/SKILL.md
- Zero formula errors -> write-scores verification (recalc error scan), final-check item 2, xlsx-rules.
- Preserve existing templates -> header/format/width copying in write_scores; plan rule 5; xlsx-rules.
- Financial-model colours, number formats, assumptions placement, hardcode documentation -> xlsx-rules "only when the task is a financial model". Deliberately not applied to scoring sheets (see design decisions).
- LibreOffice required / recalc.py usage and output interpretation -> `scripts/recalc.py` (verbatim), called by write_scores; xlsx-rules; final-check item 4.
- pandas reading/analysis -> xlsx-rules Tools (pandas is not in the container, noted).
- Formulas not hardcoded values (wrong/right examples) -> core design of write_scores; anti-pattern 1; xlsx-rules.
- Common workflow (choose tool, load, modify, save, recalc, fix errors) -> the graph itself; manual-score template.
- Creating/editing with openpyxl snippets -> xlsx-rules Tools (condensed; see drop log).
- Verification checklist (sample refs, column mapping, row offset, NaN, division by zero, cross-sheet refs, edge cases) -> xlsx-rules checklist; write_scores checks every cell; synthetic edge-case test.
- openpyxl notes (1-based, data_only loses formulas, read_only/write_only) -> xlsx-rules; anti-pattern 2.
- Code style guidelines -> xlsx-rules Code style.

senior-data-scientist/
- "Data quality validation" and "test edge cases / comprehensive testing" -> profile anomalies and write-scores verification.
- Everything else -> dropped (below).

## Deliberate-drop log

| Item | Why dropped |
|---|---|
| senior-data-scientist SKILL.md: tech stack, MLOps, deployment, latency/throughput/uptime targets, security/compliance, team leadership, common commands (pytest, docker, kubectl, helm) | Generic boilerplate unrelated to computing lifter scores in a workbook; nothing actionable for this task type. |
| senior-data-scientist scripts (`experiment_designer.py`, `feature_engineering_pipeline.py`, `model_evaluation_suite.py`) | Identical stubs: `_execute()` returns `{"success": True}` and processes nothing. Kept in `source/` only. |
| senior-data-scientist references (3 files) | Identical templated placeholder text ("Pattern 1: Distributed Processing", "Further Reading: Research papers") with no domain content. |
| powerlifting: marketing prose ("whether you're new...", "old math class joke"), source attributions, the Dots acronym anecdote | Background and tone; the formulas and rules they introduce are all carried. |
| powerlifting: Glossbrenner age multipliers (masters handicaps, ages 40-80) | The source describes them but gives no table or values, so there is nothing to apply. The reference notes they are separate multipliers outside the pack. |
| powerlifting: OpenPowerlifting `Points` rounding to 2 dp | The pack follows the task's rounding instead; the reference mentions the OPL convention. |
| xlsx: verbatim openpyxl/pandas code snippets (create/edit workbook, fonts, fills, column widths) | Agents already know these APIs; write_scores implements what the procedure needs, and xlsx-rules keeps the non-obvious pitfalls. |
| xlsx: financial-model conventions as defaults | They apply only to financial models; applying them here would change the requested layout. Kept as conditional guidance in xlsx-rules. |
| xlsx: macOS `gtimeout` detail in recalc.py usage | Kept in the verbatim script; nothing to add to the procedure. |
