# Source notes — `powerlifting` AIP skill

## Origin

Curated source: `SKILL-original.md` — narrative documentation of four powerlifting
score-normalization systems (Dots, IPF GoodLift, Wilks, Glossbrenner) with their
formulas, polynomial coefficients, and Rust reference implementations from
OpenPowerlifting.

## Schema choice

Used `procedure.schema.json` (AIP procedure category).

The original is a documentation page, but the agent-facing task is procedural:
identify which scoring system applies → gather inputs → compute a value (or build
an Excel formula). The procedure schema captures the execution graph and lets us
back the deterministic math with scripts.

## Script vs prose decisions

**Scripted (deterministic math, lookup tables, bound clamping):**
- `scripts/score.py` — single CLI that computes Dots / Wilks / IPF GoodLift
  points given `(sex, bodyweight_kg, total_kg)` plus `equipment`/`event` for
  IPF GL. Encodes the polynomial coefficients, bodyweight clamps, the IPF
  lookup table, and the sex/equipment normalization rules.
- `scripts/excel_formula.py` — emits the Excel `=...` string for the same
  systems, parameterized by sex/bw/total cell references. Needed because the
  benchmark workflow embeds formulas in a workbook rather than precomputed
  numbers; tests check for `=`-prefixed cell values.

Both files are intentionally minimal (stdlib + `argparse`) so they start fast
and don't pull a numerics dependency.

**Prose (judgment calls):**
- `identify-scoring-system` — which system to use depends on context (federation,
  user phrasing, dataset columns). That's interpretation, not a lookup.
- `gather-inputs` — mapping spreadsheet columns / user phrasing onto
  `(sex, bodyweight, total)` requires reading the data; the agent decides.

## Deliberate drops

- **Glossbrenner script.** The source documents Glossbrenner as the average of
  Schwartz-Malone and Wilks (piecewise on bodyweight), but the source SKILL.md
  does **not** include the Schwartz or Malone coefficients — they live in a
  sibling Rust module that wasn't provided. Rather than fabricate constants,
  the formula description is preserved in `references/formulas.md` (so an
  agent can still answer "how is Glossbrenner computed?") but no `score.py`
  branch ships. If a future revision provides Schwartz/Malone, add them and
  extend `score.py`. Practically, modern federations have moved off
  Glossbrenner toward Dots and IPF GL, so this gap rarely blocks tasks.
- **Rust source listings.** The source's Rust snippets duplicate the constants
  and bounds that are now encoded in `scripts/score.py` and
  `references/formulas.md`. Dropping the verbatim Rust keeps the body lean
  while preserving the underlying math.
- **External links** (powerliftpro.app, ipf.com PDFs, Wikipedia, OpenPowerlifting
  GitLab). Preserved in `references/formulas.md` for citation lookup.

## Mapping (source → AIP)

| Source content                            | Where it lives in the AIP skill                 |
|-------------------------------------------|-------------------------------------------------|
| Dots prose + formula + Rust constants     | `scripts/score.py::dots`, `excel_formula.py`, body `scenarios`, `references/formulas.md` |
| IPF GoodLift prose + lookup + Rust        | `scripts/score.py::ipf_gl` (+ `IPF_GL` table), `excel_formula.py`, `references/formulas.md` |
| Wilks coefficient table + Rust            | `scripts/score.py::wilks`, `excel_formula.py`, `references/formulas.md` |
| Glossbrenner prose + Rust (partial)       | `references/formulas.md` only (see drop above)  |
| Bodyweight clamping bounds                | Encoded as constants in `scripts/score.py` and `scripts/excel_formula.py`; cross-referenced in `anti_patterns` |
| Mx → M mapping; equipment grouping        | Helpers `_normalize_sex` / `_normalize_equipment` in `score.py`; noted in `gather-inputs` |
| Zero-bodyweight / zero-total → 0 points   | Guard clauses in `score.py`; `anti_patterns` entry |
