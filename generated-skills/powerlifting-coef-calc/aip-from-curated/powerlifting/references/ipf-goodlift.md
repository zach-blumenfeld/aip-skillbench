# IPF GoodLift (IPF GL) coefficient

The International Powerlifting Federation's current normalization, used
since 2020. Unlike DOTS / Wilks, the parameters depend on **sex,
equipment, and event** (full-power vs bench-only), not just sex.

Source: <https://www.powerlifting.sport/fileadmin/ipf/data/ipf-formula/IPF_GL_Coefficients-2020.pdf>

## Formula

```
IPF-GL = TotalKg * max(0, 100 / (A - B * exp(-C * BW)))
```

`BW` in kg. If the denominator is ≤ 0, or `BW < 35`, or the total is 0,
the score is 0.

## Parameter table

The curated source's lookup table, verbatim:

| Event | Sex | Equipment | A | B | C |
|---|---|---|---|---|---|
| SBD | M | Raw     | 1199.72839 | 1025.18162 | 0.009210 |
| SBD | M | Single  | 1236.25115 | 1449.21864 | 0.01644  |
| SBD | F | Raw     | 610.32796  | 1045.59282 | 0.03048  |
| SBD | F | Single  | 758.63878  | 949.31382  | 0.02435  |
| B   | M | Raw     | 320.98041  | 281.40258  | 0.01008  |
| B   | M | Single  | 381.22073  | 733.79378  | 0.02398  |
| B   | F | Raw     | 142.40398  | 442.52671  | 0.04724  |
| B   | F | Single  | 221.82209  | 357.00377  | 0.02937  |

Notes from the source:

- `Wraps` and `Straps` equipment are scored with the `Raw` parameters.
- `Multi-ply` and `Unlimited` are scored with the `Single-ply` parameters.
- `Mx` is scored with the `M` parameters.
- Any combination outside this table returns 0.

## Reference test vectors

- Dmitry Inzarkin, 2019 IPF World Open Men's: BW=92.04, total=1035.0,
  Single, SBD → `112.85`.
- Susanna Torronen, 2019 IPF World Classic Bench: BW=70.50, total=122.5,
  Raw, B → `96.78`.

`scripts/build_coef_workbook.py --coef goodlift --equipment <…> --event <…>`
emits the corresponding Excel formula. If `--equipment` or `--event` are
not supplied, the script defaults to `Raw` / `SBD` and surfaces the
choice in stderr.
