# Wilks coefficient

The Wilks score predates DOTS and is still in use by some federations.
Same shape — total times a bodyweight-dependent coefficient — but the
polynomial is degree 5, and coefficient indexing is reversed in the
canonical statement of the formula.

Background: <https://en.wikipedia.org/wiki/Wilks_coefficient>

## Formula

```
Wilks = TotalKg * (500 / (a + b·BW + c·BW^2 + d·BW^3 + e·BW^4 + f·BW^5))
```

## Coefficients

| | Men | Women |
|---|---|---|
| a | -216.0475144   | 594.31747775582 |
| b | 16.2606339     | -27.23842536447 |
| c | -0.002388645   | 0.82112226871   |
| d | -0.00113732    | -0.00930733913  |
| e | 7.01863e-06    | 4.731582e-05    |
| f | -1.291e-08     | -9.054e-08      |
| BW clamp | `MAX(40, MIN(201.9, BW))` | `MAX(26.51, MIN(154.53, BW))` |

Upper clamp avoids an asymptote in the polynomial; lower clamp prevents
absurd scores for very light (typically child) lifters.

## Sanity checks

From the curated source's Rust test vectors:

- `wilks_coefficient_men(100.0)` → `0.6085890719066511`
- `wilks_coefficient_women(100.0)` → `0.8325833167368228`
- `wilks(M, 100 kg, 1000 kg)` → `608.58907`
- `wilks(F, 60 kg, 500 kg)` → `557.4434`

If `scripts/build_coef_workbook.py` is invoked with `--coef wilks`, the
generated Excel formula reproduces these to within the requested rounding.
