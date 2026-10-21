# Powerlifting scoring formulas (OpenPowerlifting implementations)

Machine-readable parameters for Dots, Wilks and IPF GL are in `assets/coefficients.json`;
`scripts/build_score_sheet.py` turns them into Excel formulas. This file is for building a
sheet by hand (Glossbrenner or anything the script does not cover) or for checking values.

## Shared rules

- Total = Best3SquatKg + Best3BenchKg + Best3DeadliftKg (kg). Bodyweight = BodyweightKg on meet day.
- Sex `M` and `Mx` use the men's parameters; `F` uses the women's.
- Zero bodyweight (unknown) or zero total -> 0 points.
- Points = coefficient x total.

## Dots (Dynamic Objective Team Scoring; BVDK / Tim Konertz)

Normalises a total by bodyweight so lifters of all weights and sexes can be compared.

    coefficient = 500 / (A*x^4 + B*x^3 + C*x^2 + D*x + E)

| | A | B | C | D | E | x clamp |
|---|---|---|---|---|---|---|
| Men (M, Mx) | -0.0000010930 | 0.0007391293 | -0.1918759221 | 24.0900756 | -307.75076 | [40, 210] |
| Women (F)   | -0.0000010706 | 0.0005158568 | -0.1126655495 | 13.6175032 | -57.96288 | [40, 150] |

Bodyweights outside the clamp are set to the boundary. Men at 100 kg -> coefficient 0.61552.

## IPF GL (Good Lift) coefficient

    points = total * max(0, 100 / (A - B * e^(-C * BWT)))

0 when bodyweight < 35 kg, total is 0, the denominator is 0, or no parameters apply.
Equipment folds to two groups: Raw, Wraps, Straps -> Raw; Single-ply, Multi-ply, Unlimited -> Single.
Only events SBD (full power) and B (bench only) have parameters; all others score 0.

| Event | Sex | Equip | A | B | C |
|---|---|---|---|---|---|
| SBD | M | Raw | 1199.72839 | 1025.18162 | 0.009210 |
| SBD | M | Single | 1236.25115 | 1449.21864 | 0.01644 |
| SBD | F | Raw | 610.32796 | 1045.59282 | 0.03048 |
| SBD | F | Single | 758.63878 | 949.31382 | 0.02435 |
| B | M | Raw | 320.98041 | 281.40258 | 0.01008 |
| B | M | Single | 381.22073 | 733.79378 | 0.02398 |
| B | F | Raw | 142.40398 | 442.52671 | 0.04724 |
| B | F | Single | 221.82209 | 357.00377 | 0.02937 |

Published checks: M, Single-ply, SBD, 92.04 kg, 1035 kg -> 112.85. F, Raw, B, 70.50 kg, 122.5 kg -> 96.78.

## Wilks

    coefficient = 500 / (a + b*x + c*x^2 + d*x^3 + e*x^4 + f*x^5)

| | a | b | c | d | e | f | x clamp |
|---|---|---|---|---|---|---|---|
| Men   | -216.0475144 | 16.2606339 | -0.002388645 | -0.00113732 | 7.01863e-06 | -1.291e-08 | [40, 201.9] |
| Women | 594.31747775582 | -27.23842536447 | 0.82112226871 | -0.00930733913 | 4.731582e-05 | -9.054e-08 | [26.51, 154.53] |

Upper clamp avoids the polynomial's asymptote; lower clamp avoids huge coefficients for children.
Checks: men 100 kg -> 0.6085890719066511; women 100 kg -> 0.8325833167368228;
M 100 kg / 1000 kg -> 608.58907; F 60 kg / 500 kg -> 557.4434.

## Glossbrenner (GPC affiliates) — not scriptable from these sources

Product number = lifter's total x Glossbrenner bodyweight coefficient. Piecewise:

- Men: bw < 153.05 -> (Schwartz(bw) + WilksMen(bw)) / 2; else (Schwartz(bw) + (-0.000821668402557*bw + 0.676940740094416)) / 2
- Women: bw < 106.3 -> (Malone(bw) + WilksWomen(bw)) / 2; else (Malone(bw) + (-0.000313738002024*bw + 0.852664892884785)) / 2

Schwartz (men) and Malone (women) coefficients are not given in the source material; obtain them
from the OpenPowerlifting `schwartzmalone` module before building this score.
Checks: men 100 kg -> 0.5812707859533183; women 100 kg -> 0.7152488066040259;
M 100 kg / 1000 kg -> 581.27; F 60 kg / 500 kg -> 492.53032; bodyweight 0 -> 0.

Glossbrenner also has masters age multipliers (ages 40-80) published by the WPC; they are a
separate age handicap, applied only when the task asks for age-adjusted scores.

## OpenPowerlifting data columns that matter

- `Sex`: M, F, or Mx.
- `Event`: SBD, BD, SD, SB, S, B, D (which lifts were contested).
- `Equipment`: Raw, Wraps, Single-ply, Multi-ply, Unlimited, Straps.
- `BodyweightKg`: optional, two decimals; blank means unknown.
- `Best3SquatKg/BenchKg/DeadliftKg`: optional; rarely negative (lowest failed attempt).
- `TotalKg`: in OPL exports, blank when any lift failed or the lifter was disqualified.
- `Name`: duplicates are disambiguated with `#1`, `#2`; copy names verbatim.
