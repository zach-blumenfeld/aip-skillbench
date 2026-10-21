# Provenance

Compiled 2026-10-20 into `powerlifting-scores-xlsx` from three curated skills, copied verbatim here:

| Path | What it contributed |
|---|---|
| `powerlifting/SKILL.md` | Dots, IPF GOODLIFT, Wilks, and Glossbrenner formulas, coefficients, clamps, edge rules, and test fixtures (OpenPowerlifting Rust code). |
| `xlsx/SKILL.md`, `xlsx/recalc.py`, `xlsx/LICENSE.txt` | Formulas-not-values rule, openpyxl/pandas workflow, LibreOffice recalculation, error scan, and verification checklist. `recalc.py` is mirrored to `scripts/recalc.py` with only a requirements header added. The license terms in `xlsx/LICENSE.txt` apply to that script. |
| `senior-data-scientist/` (SKILL.md, 3 references, 3 scripts) | Generic boilerplate. Nothing task-specific (see drop log). |

The task's `data-readme.md` (environment input, not a skill) supplied the data semantics the scripts encode: a negative Best3 value is a failed attempt, a failed lift means no TotalKg, sex values are `M`/`F`/`Mx`, and the meanings of Event and Equipment.

Intent: one skill that turns an OpenPowerlifting-style "Data" sheet into a score sheet of live formulas (copied input columns → `TotalKg` → `Dots`) with fixed-decimal rounding, recalculated and verified. It generalizes to reordered columns, a pre-existing TotalKg column, bench-only rows, and the Wilks/GOODLIFT variants.

# Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Environment check | instruction (one-line commands) | Trivial. The body says to name anything missing. |
| `task_reading` (score, digits, round_coefficient) | decision | Interpreting the task wording is a judgment over a fixed answer space. The answers become script flags. |
| Column selection, sheet layout, TotalKg and score formulas | script (`score_sheet.py build`) | Deterministic rules: header lookup, source order, coefficient lookup tables, clamps, Mx→men, failed-lift and zero rules, rounding. |
| Recalculation and error scan | script (`recalc.py`, from the xlsx skill) | Mechanical. Needed so cached values exist. |
| Correctness check | script (`score_sheet.py verify`) | Compares each cell to an independent Python port of the OpenPowerlifting functions, a deterministic validation loop. |
| Final summary | client task | Free-text output for the user. |
| Glossbrenner | reference only | The source lacks the Schwartz/Malone coefficients, so it cannot be scripted faithfully. Formula, constants, and fixtures are kept in `references/coefficients.md`, and the body says to get the missing coefficients first. |

Design notes:
- Coefficients live inside each formula rather than in assumption cells. The xlsx guideline prefers assumption cells, but the task fixes the sheet layout (copied columns, then TotalKg, then Dots), so extra cells would break it. This is recorded as a gotcha.
- Rounding: by default `ROUND(...,d)` is applied to TotalKg and the final score only. That is the least distorting reading of "keep 3 digits precision for all computation". `--round-coefficient` exists for tasks that explicitly ask for the coefficient to be rounded.
- Failed lifts (negative Best3) give TotalKg 0 and a score of 0, following the readme ("TotalKg is empty") and the Rust rule that a zero total gives zero points. 0 is used instead of blank so the downstream formula never errors.

# Deliberate-drop log

| Source content | Rationale |
|---|---|
| powerlifting: marketing/explanatory prose on what DOTS is, "old math class joke", links to powerliftpro exercise pages | Background. The agent needs only the formula and coefficients. |
| powerlifting: garbled inline formula text ("DOTS Score=Total…×a+b(BW)…500") | Replaced by the exact formula from the Rust code. |
| powerlifting: Dots history (BVDK, IPF Points not cross-sex, Wilks ostracized, author e-mail) | History. It is summarized in a one-line attribution in coefficients.md. |
| powerlifting: IPF GL calculator UI instructions ("Choose units and enter…") | UI text for a web calculator. The inputs it lists (bodyweight, gender, lift type, i.e. classic/equipped × power/bench) are carried as the GL parameter table and equipment mapping. |
| powerlifting: Glossbrenner masters age-multiplier history paragraph | Background. The table itself is not in the source. coefficients.md notes that age multipliers are a separate table that is not included. |
| powerlifting: Rust `use`/type plumbing (`Points`, `WeightKg`, `poly4` import) | Implementation detail. The semantics are ported to `score_sheet.py`. |
| xlsx: "Works on both Linux and macOS" and other script marketing | Not actionable. |
| xlsx: financial-model color coding and number formats | Not used by the score task. Kept in `references/xlsx-guidelines.md` (load on demand), so this is not dropped. |
| senior-data-scientist/SKILL.md: tech stack, production patterns (scaling, deployment, real-time inference), latency/throughput/availability targets, security/compliance, team leadership, common commands (pytest, docker, kubectl, helm) | Generic boilerplate with no bearing on computing scores in a workbook. The one transferable idea, validating data quality and results, is realized as `score_sheet.py verify`. |
| senior-data-scientist/references/*.md (3 files) | Identical template text apart from the title ("handle 10x load", "99.9% uptime", generic best practices). No domain content. |
| senior-data-scientist/scripts/*.py (3 files) | Stubs. `_execute()` returns `{"success": True}` without doing anything, and the CLI flags are unused. Running them would only mislead. |
