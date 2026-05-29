# Source notes — powerlifting coefficient skill

## Origin

Compiled from `SKILL.original.md`, the curated Anthropic skill bundled at
`vendor/skillsbench/tasks/powerlifting-coef-calc/environment/skills/powerlifting/SKILL.md`.

The curated skill is a single markdown body that mixes prose, references,
and Rust reference implementations (from the OpenPowerlifting `opl-data`
crate, GPL-3.0+) for four normalization formulas:

- **DOTS** (Dynamic Objective Team Scoring) — quartic polynomial in BW
- **IPF GoodLift** — `100 / (A - B·exp(-C·BW))`, by sex/equipment/event
- **Wilks** — quintic polynomial in BW
- **Glossbrenner** — piecewise average of Schwartz-Malone and Wilks

## Intent

An autonomous agent invoking this skill needs to compute normalized
powerlifting scores for a spreadsheet of lifters and write the answer back
into Excel **as formulas, not literals** — so that a downstream test that
opens the file with `openpyxl` and checks `cell.value.startswith("=")`
will pass. Three-digit rounding is expected for DOTS scoring rows.

## Schema choice

`source/procedure.schema.json` (AIP `procedure`) — this is a multi-step
execution graph: inspect workbook → choose coefficient → build formula →
write output → verify. Conditional logic (formula selection by sex /
coefficient family) is pushed into `scripts/`, prose stays in the body.

## Scripts

- `scripts/build_coef_workbook.py` — single entrypoint. Reads the input
  `.xlsx`, copies the named source sheet, appends a target sheet with
  Excel formula references for selected columns, and writes a `TotalKg`
  sum formula plus a coefficient formula (DOTS / Wilks / GoodLift /
  Glossbrenner) rounded to a configurable precision. All constants live
  in this script so the body never restates them.

## Mapping audit

Every distinct piece of the source SKILL.md is classified:

| Source content                                                  | Status         | Where it lives now |
|-----------------------------------------------------------------|----------------|--------------------|
| DOTS description and use case                                   | Mapped         | `references/dots.md` |
| DOTS male/female polynomial coefficients and BW clamps          | Mapped         | `scripts/build_coef_workbook.py` (constants) + `references/dots.md` |
| DOTS Rust implementation                                        | Mapped         | Re-expressed as Excel formula in `build_coef_workbook.py`; rationale in `references/dots.md` |
| IPF GoodLift formula `100 / (A − B·e^(−C·BWT))`                  | Mapped         | `references/ipf-goodlift.md` + script |
| IPF GoodLift parameter table (sex × equipment × event)           | Mapped         | `scripts/build_coef_workbook.py` (lookup table) + reference |
| Wilks quintic formula and male/female coefficients               | Mapped         | `references/wilks.md` + script |
| Wilks BW clamps (40–201.9 men; 26.51–154.53 women)               | Mapped         | `scripts/build_coef_workbook.py` |
| Glossbrenner piecewise definition and linear-tail constants      | Mapped         | `references/glossbrenner.md` + script |
| Schwartz-Malone helpers (Glossbrenner dependencies)              | Deliberate drop | Schwartz-Malone coefficients are not published in the curated source; Glossbrenner support is therefore best-effort and documented as such in `references/glossbrenner.md` |
| Rust `Points::from_i32(0)` zero-bodyweight / zero-total handling | Mapped         | Replicated as `IFERROR`/zero-guards in Excel formula |
| Author attribution (Tim Konertz for DOTS)                       | Mapped         | `references/dots.md` |
| External URLs (powerliftpro, IPF PDF, Wikipedia, GPC)           | Mapped         | `references/*.md` |
