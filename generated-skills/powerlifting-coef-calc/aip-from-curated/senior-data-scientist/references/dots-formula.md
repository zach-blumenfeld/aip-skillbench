# Dots Coefficient Formula (IPF / OpenPowerlifting)

The Dots score is a sex- and bodyweight-adjusted strength score used to compare
powerlifters of different bodyweight classes and sexes on a single scale.

Source: https://gitlab.com/openpowerlifting/opl-data/-/tree/main/crates/coefficients/src

## Formula

```
Dots = TotalKg * (500 / denominator(BodyweightKg, Sex))

denominator(bw, sex) =
    a*bw^4 + b*bw^3 + c*bw^2 + d*bw + e
```

The polynomial coefficients (`a..e`) depend on `Sex`. Bodyweight is clamped to
sex-specific bounds before evaluation.

## Coefficients

### Male (`Sex == "M"`)

| Coef | Value           |
|------|-----------------|
| a    | -0.0000010930   |
| b    |  0.0007391293   |
| c    | -0.1918759221   |
| d    | 24.0900756      |
| e    | -307.75076      |

Bodyweight clamp: **40 ≤ bw ≤ 210** (kg).

### Female (`Sex == "F"`)

| Coef | Value            |
|------|------------------|
| a    | -0.0000010706    |
| b    |  0.0005158568    |
| c    | -0.1126655495    |
| d    | 13.6175032       |
| e    | -57.96288        |

Bodyweight clamp: **40 ≤ bw ≤ 150** (kg).

## Precision

Round the final Dots score to **3 decimal places**.

## Excel encoding

The score lives on the Dots sheet and is computed by an Excel formula (not a
pre-computed numeric value). The exact formula shape, with cell references
`{sex_cell}`, `{bw_cell}`, `{total_cell}`:

```
=ROUND(
  IF({sex_cell}="M",
    {total_cell}*(500/(
      -0.0000010930*POWER(MAX(40,MIN(210,{bw_cell})),4)
      +0.0007391293*POWER(MAX(40,MIN(210,{bw_cell})),3)
      -0.1918759221*POWER(MAX(40,MIN(210,{bw_cell})),2)
      +24.0900756*MAX(40,MIN(210,{bw_cell}))
      -307.75076
    )),
    {total_cell}*(500/(
      -0.0000010706*POWER(MAX(40,MIN(150,{bw_cell})),4)
      +0.0005158568*POWER(MAX(40,MIN(150,{bw_cell})),3)
      -0.1126655495*POWER(MAX(40,MIN(150,{bw_cell})),2)
      +13.6175032*MAX(40,MIN(150,{bw_cell}))
      -57.96288
    ))
  ),
3)
```

Use `scripts/dots_formula.py` to emit a correctly-shaped formula for given
cell references — do not hand-author this polynomial.

## Gotchas

- Two distinct coefficient sets *and* two distinct bodyweight clamps. Easy to
  swap one and forget the other.
- The clamp is `MAX(40, MIN(upper, bw))` — *both* sides matter. Lifters below
  40 kg or above the upper bound still get a score, scored at the clamp value.
- `ROUND` wraps the entire `IF`, not each branch — wrapping twice is harmless
  but uglier and looks wrong on review.
- The formula multiplies `500 / polynomial` by `Total`. Some sources express
  it as `Total * 500 / polynomial`; the math is identical but parentheses
  matter — keep `500/poly` grouped.
- `Sex` values can include `Mx` in the wider OpenPowerlifting dataset. This
  task's cleaned input contains only `M` and `F`; the `IF(Sex="M", ..., ...)`
  pattern routes anything non-`M` to the female branch. Verify the input
  contains no `Mx` rows before relying on this.
