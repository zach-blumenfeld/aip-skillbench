---
name: powerlifting
description: "Calculate powerlifting score-normalization coefficients (Dots, IPF GoodLift, Wilks, Glossbrenner) that compare lifters across bodyweights and sexes. Returns a numeric points value for a (sex, bodyweight, total) tuple, or emits Excel formula strings that reference per-row cells for spreadsheet workflows. Use when scoring meet results, populating a Dots / Wilks / GL Points column in a workbook, reproducing OpenPowerlifting-style points, or answering 'who lifted more relative to their bodyweight?'."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute powerlifting score-normalization coefficients — Dots, IPF GoodLift,
  Wilks, and Glossbrenner — that normalize a lifter's total across bodyweight
  (and, in the case of Dots/Wilks/IPF-GL, across sex) so competitors in different
  weight classes can be compared on a single scale. Produces either a numeric
  points value for one (sex, bodyweight, total) tuple, or an Excel formula
  string for embedding the calculation into a spreadsheet column.

trigger_when:
  - User asks for "Dots", "IPF GL"/"GoodLift", "Wilks", "Glossbrenner", or "powerlifting score / points / coefficient".
  - Comparing lifters across weight classes or sexes.
  - Filling a "Dots", "Wilks", "GL Points", or similar column in a spreadsheet of meet results.
  - Reproducing OpenPowerlifting / OpenIPF-style coefficient columns.
  - Generating Excel formulas that reference per-row Sex / BodyweightKg / TotalKg.
  - User mentions OpenPowerlifting, OpenIPF, IPF, BVDK, GPC, USAPL, USPA in a scoring context.

do_not_use_when:
  - User wants raw totals, 1RM estimates, or training percentages — not a normalized score.
  - User wants age-only adjustments (Masters multipliers) without bodyweight normalization.
  - Task is about training programming or meet logistics, not competition scoring.

scope_and_approval: >
  All steps are read-only or produce text output. The compute scripts read no
  files and write no state. When writing Excel formulas into a workbook, prefer
  copying the source to a new file and modifying the copy rather than mutating
  the source in place — confirm with the user if the source must be edited
  directly.

steps:
  - name: identify-scoring-system
    description: >
      Pick the scoring system. Default order if the user is non-specific:
      Dots (modern federation default, sex- and bodyweight-aware, no equipment dependency)
      → IPF GoodLift (when the dataset carries Equipment + Event columns and the context is IPF/IPF-affiliated)
      → Wilks (legacy datasets, or when the user names it explicitly)
      → Glossbrenner (GPC-affiliated, only when named explicitly; see anti_patterns — script not provided).
      If the spreadsheet column is literally labeled "Dots" or "Wilks" or "GoodLift" or "GL Points", use that.
    outputs:
      - name: system
        type: string
        description: One of `dots`, `wilks`, `ipf-gl`, `glossbrenner`.

  - name: gather-inputs
    description: >
      Collect the required inputs per system. All systems need sex (M / F / Mx;
      Mx maps to M), bodyweight in kilograms, and total in kilograms. IPF GL
      additionally needs equipment (Raw/Wraps/Straps → Raw lookup;
      Single/Multi/Unlimited → Single-ply lookup) and event (SBD for full power,
      B for bench-only). If individual lift columns are provided instead of a
      total, sum Best3SquatKg + Best3BenchKg + Best3DeadliftKg. Convert pounds
      to kilograms before calling the scripts.
    inputs:
      - name: system
        type: string
    outputs:
      - name: inputs
        type: object
        description: Keys `sex`, `bodyweight_kg`, `total_kg`; for `ipf-gl` also `equipment`, `event`.

  - name: compute-points
    description: >
      Numeric coefficient calculation. Handles bodyweight clamping, sex/equipment
      normalization, and the IPF GL lookup table. Use this branch when the
      deliverable is a number (single lifter score, batch CSV column, comparison).
    script: scripts/score.py
    inputs:
      - name: system
        type: string
      - name: inputs
        type: object
    outputs:
      - name: points
        type: float
        description: Rounded to 3 decimals by default; pass `--round -1` to disable.

  - name: build-excel-formula
    description: >
      Emit an Excel formula string with the sex / bw / total / equipment / event
      cell references baked in. Use this branch when the deliverable is a
      spreadsheet whose cells must contain live formulas (e.g., tests verify
      cell.value.startswith("=")). The output goes verbatim into a cell.
    script: scripts/excel_formula.py
    inputs:
      - name: system
        type: string
      - name: sex_cell
        type: string
        description: e.g. "B2"
      - name: bw_cell
        type: string
      - name: total_cell
        type: string
      - name: equipment
        type: string
        nullable: true
        description: required for `ipf-gl`; passed as a literal, not a cell reference
      - name: event
        type: string
        nullable: true
        description: required for `ipf-gl`; passed as a literal, not a cell reference
    outputs:
      - name: formula
        type: string
        description: Begins with `=ROUND(IF(...))`. Write directly to the target cell.

  - name: emit-or-write
    description: >
      Deliver the result. For numeric requests, return the points value
      (rounded per convention — 3 decimals for Dots/Wilks, 2 for IPF GL). For
      spreadsheet workflows, write the formula into the target cell using the
      host environment's Excel library (openpyxl `cell.value`, xlsxwriter
      `write_formula`, etc.) — and also fill any precursor columns the formula
      references (e.g., a `TotalKg` column that sums the three lifts via
      `=D{row}+E{row}+F{row}`). Verify the row count matches the source sheet.

modes:
  - name: single-value
    body: >
      One lifter, one number. `uv run scripts/score.py --system <s> --sex <s> --bodyweight-kg <bw> --total-kg <t>`.
      No spreadsheet involved.
  - name: batch-formula
    body: >
      Populate an Excel column with formulas, one per row. For each data row,
      call `scripts/excel_formula.py` with the appropriate cell references and
      write the returned string to the target cell. Faster than computing each
      number in Python because Excel re-evaluates if upstream data changes,
      and many benchmark tasks specifically check for `=`-prefixed cells.
  - name: batch-precomputed
    body: >
      Populate an Excel column with computed numbers (not formulas). Loop with
      `scripts/score.py` per row. Use when the consumer wants static values or
      when formula-based outputs would break a downstream pipeline.

scenarios:
  - need: Single male lifter Dots — 92.04 kg bodyweight, 1035 kg total.
    action: "`uv run scripts/score.py --system dots --sex M --bodyweight-kg 92.04 --total-kg 1035`"
    outcome: Returns ~612 points (sex M branch, bodyweight inside [40, 210] so no clamp).

  - need: Single female lifter Wilks — 60 kg bodyweight, 500 kg total.
    action: "`uv run scripts/score.py --system wilks --sex F --bodyweight-kg 60 --total-kg 500`"
    outcome: Returns ~557.443 points — matches the OpenPowerlifting reference.

  - need: IPF GoodLift for Dmitry Inzarkin — M, 92.04 kg, 1035 kg, Single-ply, SBD.
    action: "`uv run scripts/score.py --system ipf-gl --sex M --bodyweight-kg 92.04 --total-kg 1035 --equipment Single --event SBD --round 2`"
    outcome: Returns 112.85 — the published IPF reference value.

  - need: Populate a "Dots" sheet in openipf.xlsx with live formulas referencing the Data sheet.
    context: >
      Data sheet has columns Name (A), Sex (B), …, BodyweightKg (I), …,
      Best3SquatKg (K), Best3BenchKg (L), Best3DeadliftKg (M). The Dots sheet
      needs columns Name, Sex, BodyweightKg, Best3SquatKg, Best3BenchKg,
      Best3DeadliftKg, TotalKg, Dots with matching row count.
    action: >
      For each row r ≥ 2, write `=Data!A{r}` … `=Data!M{r}` references into
      columns A–F of the Dots sheet, then `=D{r}+E{r}+F{r}` into column G
      (TotalKg). Call `scripts/excel_formula.py --system dots --sex-cell B{r}
      --bw-cell C{r} --total-cell G{r}` and write its output into column H.
      Use xlsxwriter `write_formula` (or openpyxl equivalent).
    outcome: >
      Dots column shows live formulas that recompute when Data changes. Tests
      that load the workbook with openpyxl see `cell.value` starting with `=`
      and containing both `ROUND(` and `IF(`.

anti_patterns:
  - >
    Forgetting to clamp bodyweight. Each system has a different range — Dots M
    [40, 210], Dots F [40, 150], Wilks M [40, 201.9], Wilks F [26.51, 154.53],
    IPF GL minimum 35. The scripts clamp automatically; if you re-derive the
    formula by hand, replicate the clamp or you'll get wrong points for very
    light or very heavy lifters.
  - >
    Mapping Mx to female. Every system in scope maps `Mx` to the male table
    (per OpenPowerlifting convention). The `_normalize_sex` helper does this;
    don't override it.
  - >
    Skipping ROUND in spreadsheet outputs. Downstream tests typically compare
    with a small tolerance against pre-rounded ground truth. Apply `ROUND`
    inside the Excel formula (the scripts do this by default with 3 decimals
    for Dots/Wilks, override with `--round` for IPF GL's 2-decimal convention).
  - >
    Reversing Wilks polynomial direction. Wilks is defined ascending
    (`a + b*x + c*x^2 + …`). The Rust reference passes coefficients to a
    `poly5` helper in descending order, which is easy to mis-port. `score.py`
    and `excel_formula.py` are the authoritative implementations.
  - >
    Calling IPF GL without equipment/event. The lookup returns (0, 0, 0) for
    undefined combinations and points fall to 0. Always pass `--equipment` and
    `--event`, and warn the user if the dataset's Event column has values
    other than SBD or B (S/D/SD/BD are not in the IPF GL table).
  - >
    Treating zero bodyweight or zero total as a valid input. By convention
    both ⇒ 0 points; the scripts already short-circuit. Don't try to "fix" a
    missing bodyweight by substituting a class boundary.
  - >
    Implementing Glossbrenner from the curated source alone. Glossbrenner
    averages Schwartz/Malone with Wilks, but the Schwartz/Malone constants
    are NOT in the curated SKILL.md and the script does not implement
    Glossbrenner. If a user asks for it, surface the gap and fall back to
    Dots or Wilks rather than fabricating coefficients. See
    `references/formulas.md` for the formula skeleton.
  - >
    Confusing IPF GL with the older "IPF Points" formula. IPF GL is the
    current (2020+) IPF official scoring; IPF Points is the prior system and
    is not covered here.
```
