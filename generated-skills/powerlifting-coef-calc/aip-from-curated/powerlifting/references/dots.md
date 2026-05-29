# DOTS — Dynamic Objective Team Scoring

DOTS normalizes a powerlifting total against the lifter's bodyweight so
performances are comparable across weight classes and sexes. Author: Tim
Konertz (BVDK / IPF Germany).

Source background: <https://powerliftpro.app/understanding-the-dots-score-in-powerlifting-a-comprehensive-guide/>

## Formula

```
DOTS = TotalKg * (500 / (a·BW^4 + b·BW^3 + c·BW^2 + d·BW + e))
```

`BW` is bodyweight in kg, clamped to a sex-specific range before being
substituted into the polynomial. The total is the sum of the best
successful squat, bench, and deadlift in kg.

## Coefficients

| | Men (`Sex = M` or `Mx`) | Women (`Sex = F`) |
|---|---|---|
| a | -0.0000010930 | -0.0000010706 |
| b | 0.0007391293  | 0.0005158568  |
| c | -0.1918759221 | -0.1126655495 |
| d | 24.0900756    | 13.6175032    |
| e | -307.75076    | -57.96288     |
| BW clamp | `MAX(40, MIN(210, BW))` | `MAX(40, MIN(150, BW))` |

`Mx` (gender-neutral) is scored with the men's coefficients.

## Edge cases

- Zero bodyweight or zero total → score is 0. Guard with `IF(BW=0, 0, …)`
  in Excel, or rely on the upstream filter that drops empty rows.
- Bodyweights outside the clamp interval do not raise an error; the
  polynomial is evaluated at the clamp boundary instead.

## Reference implementation (from the curated source)

```rust
pub fn dots_coefficient_men(bodyweightkg: f64) -> f64 {
    const A: f64 = -0.0000010930;
    const B: f64 = 0.0007391293;
    const C: f64 = -0.1918759221;
    const D: f64 = 24.0900756;
    const E: f64 = -307.75076;
    let adjusted = bodyweightkg.clamp(40.0, 210.0);
    500.0 / poly4(A, B, C, D, E, adjusted)
}
```

`scripts/build_coef_workbook.py` emits the equivalent Excel formula. The
coefficients are duplicated there so the workbook-builder is the single
source of truth at runtime — do not retype them into the body.
