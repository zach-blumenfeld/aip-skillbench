# Glossbrenner coefficient

Glossbrenner is a piecewise average of two older systems — Schwartz-Malone
(below a BW cutoff) and Wilks (above it), with a linear tail. It is most
commonly used by GPC affiliates.

Source: <https://worldpowerliftingcongress.com/wp-content/uploads/2015/02/Glossbrenner.htm>

## Formula

```
Glossbrenner = TotalKg * GBC(sex, BW)
```

### Men

```
if BW < 153.05:
    GBC = (schwartz(BW) + wilks_men(BW)) / 2
else:
    GBC = (schwartz(BW) + (-0.000821668402557 * BW + 0.676940740094416)) / 2
```

### Women

```
if BW < 106.3:
    GBC = (malone(BW) + wilks_women(BW)) / 2
else:
    GBC = (malone(BW) + (-0.000313738002024 * BW + 0.852664892884785)) / 2
```

## Schwartz-Malone dependency

The curated source SKILL.md references `schwartz_coefficient` and
`malone_coefficient` from a sibling module but does not include their
constants in the body. `scripts/build_coef_workbook.py` therefore treats
Glossbrenner as **best-effort**: it falls back to the published
sanity-check values where it can but does not emit a closed-form Excel
formula. If the task requires Glossbrenner, prefer computing scores in
Python (the script's `--coef glossbrenner --emit-values` mode writes
literal numbers instead of formulas) and tell the user the cell will not
be a live formula.

## Sanity checks (men=100kg, total=1000kg; women=60kg, total=500kg)

- `glossbrenner_coefficient_men(100.0)` → `0.5812707859533183`
- `glossbrenner_coefficient_women(100.0)` → `0.7152488066040259`
- `glossbrenner(M, 100, 1000)` → `581.27`
- `glossbrenner(F, 60, 500)` → `492.53032`
- Zero BW or zero total → 0.
