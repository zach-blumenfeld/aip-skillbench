# Dots Coefficient — Formula Reference

The Dots coefficient normalizes a lifter's competition total against bodyweight
so lifters across weight classes can be compared on a single scale. It is the
current OpenPowerlifting / IPF preferred scoring system, having replaced Wilks
for most rankings.

## Definition

```
Dots = TotalKg × (500 / poly(BodyweightKg, Sex))
```

where `poly` is a sex-specific quartic in bodyweight with the input first
clamped to a sex-specific range.

## Polynomial form

```
poly(bw) = a·bw⁴ + b·bw³ + c·bw² + d·bw + e
```

## Coefficients (OpenPowerlifting canonical values)

Source: <https://gitlab.com/openpowerlifting/opl-data/-/tree/main/crates/coefficients/src>

### Male

| coef | value           |
|------|-----------------|
| a    | -0.0000010930   |
| b    |  0.0007391293   |
| c    | -0.1918759221   |
| d    | 24.0900756      |
| e    | -307.75076      |

**Bodyweight clamp:** `bw → MAX(40, MIN(210, bw))`

### Female

| coef | value           |
|------|-----------------|
| a    | -0.0000010706   |
| b    |  0.0005158568   |
| c    | -0.1126655495   |
| d    | 13.6175032      |
| e    | -57.96288       |

**Bodyweight clamp:** `bw → MAX(40, MIN(150, bw))`

## Sex handling

The OpenPowerlifting schema permits `M`, `F`, or `Mx`. The Dots polynomial is
defined only for `M` and `F`. The standard Excel encoding is:

```
=IF(Sex="M", male_dots, female_dots)
```

which routes `Mx` and any other non-`M` value through the female polynomial.
This matches the OpenPowerlifting reference implementation and is the
convention to follow unless the user specifies otherwise.

## Final formula skeleton (Excel)

For a row where Sex is in `B{row}`, BodyweightKg in `C{row}`, TotalKg in
`G{row}`:

```
=ROUND(
  IF(
    B{row}="M",
    G{row} * (500 / (
      A_M * POWER(MAX(40,MIN(210,C{row})),4)
      + B_M * POWER(MAX(40,MIN(210,C{row})),3)
      + C_M * POWER(MAX(40,MIN(210,C{row})),2)
      + D_M * MAX(40,MIN(210,C{row}))
      + E_M
    )),
    G{row} * (500 / (
      A_F * POWER(MAX(40,MIN(150,C{row})),4)
      + B_F * POWER(MAX(40,MIN(150,C{row})),3)
      + C_F * POWER(MAX(40,MIN(150,C{row})),2)
      + D_F * MAX(40,MIN(150,C{row}))
      + E_F
    ))
  ),
  3
)
```

The `ROUND(..., 3)` wraps only the outer IF result. Do not round the inner
polynomial — that loses precision before the division.

## Sanity-check examples

These are approximate values (compute exactly via the formula above; rounding
of intermediate steps will shift the last digit):

| Sex | BodyweightKg | TotalKg | Dots ≈ |
|-----|--------------|---------|--------|
| M   | 83.0         | 700     | ≈ 467  |
| M   | 120.0        | 900     | ≈ 491  |
| F   | 63.0         | 400     | ≈ 405  |
| F   | 84.0         | 500     | ≈ 446  |

If the script output is more than ±5 points off these reference figures,
suspect a coefficient typo or a clamp / sex-branch bug.

## Related coefficients (not implemented here)

- **Wilks / Wilks2020** — older normalization; different polynomial.
- **IPF Points / IPF GL Points** — equipment-aware, includes Single-ply
  and Multi-ply categories; logarithmic, not polynomial.
- **SBD-Score** — composite per-lift score, not a single coefficient.

Confirm with the user if they ask for a "powerlifting score" without naming
Dots — these formulas are not interchangeable.
