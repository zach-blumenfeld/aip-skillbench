# Powerlifting scoring formulas (OpenPowerlifting implementations)

`scripts/pl_lib.py` implements all of these twice: as Python reference functions and as Excel formula builders. This file is for checking or explaining a result, or for hand work outside the scripts.

Common rules:
- Sex: `F` uses the women's constants; `M` and `Mx` use the men's.
- Points = coefficient x total (kg). Bodyweight 0 or total 0 gives 0 points (0 bodyweight = unknown).
- The total is Best3Squat + Best3Bench + Best3Deadlift for full power (SBD). OpenPowerlifting leaves TotalKg empty when any lift failed (negative Best3 value = heaviest failed attempt) or the lifter was disqualified, so those lifters score 0.
- All inputs are kilograms (1 lb = 0.45359237 kg). The IPF GL calculator's lift types map as: Classic Power Lift = SBD Raw, Equipped Power Lift = SBD Single-ply, Classic Bench Press = B Raw, Equipped Bench Press = B Single-ply.
- OpenPowerlifting stores points rounded to 2 decimals (`Points::from`); follow the task's rounding instead.

## Dots (Dynamic Objective Team Scoring)

Coefficient = 500 / (A*BW^4 + B*BW^3 + C*BW^2 + D*BW + E), BW clamped to the range ("bodyweights out of range match the boundaries").

| | A | B | C | D | E | BW clamp |
|---|---|---|---|---|---|---|
| Men (M, Mx) | -0.0000010930 | 0.0007391293 | -0.1918759221 | 24.0900756 | -307.75076 | 40-210 |
| Women | -0.0000010706 | 0.0005158568 | -0.1126655495 | 13.6175032 | -57.96288 | 40-150 |

Note the source page's prose "Total x a+b(BW)+... 500" is a garbled rendering; the Rust `poly4(A,B,C,D,E,x)` means A is the x^4 coefficient. Dots was introduced by the German IPF affiliate BVDK for mixed-sex team competitions after the IPF moved to IPF Points; author Tim Konertz.

## Wilks

Coefficient = 500 / (a + b x + c x^2 + d x^3 + e x^4 + f x^5), x = bodyweight in kg, clamped.

| | a | b | c | d | e | f | BW clamp |
|---|---|---|---|---|---|---|---|
| Men | -216.0475144 | 16.2606339 | -0.002388645 | -0.00113732 | 7.01863e-06 | -1.291e-08 | 40-201.9 |
| Women | 594.31747775582 | -27.23842536447 | 0.82112226871 | -0.00930733913 | 0.00004731582 | -0.00000009054 | 26.51-154.53 |

Upper clamp avoids the asymptote; lower clamp avoids huge coefficients for children.
Test values: men coef(100) = 0.6085890719066511; women coef(100) = 0.8325833167368228; wilks(M, 100, 1000) = 608.58907; wilks(F, 60, 500) = 557.4434.

## IPF GL (Good Lift) points

Points = total x max(0, 100 / (A - B * e^(-C * BW))).

Equipment mapping (the formula only covers Raw and Single-ply): Raw, Wraps, Straps -> Raw; Single-ply, Multi-ply, Unlimited -> Single-ply. Mx -> men. Only events SBD and B (bench only) are defined; any other event gives 0. Bodyweight < 35 kg, total 0, or a zero denominator give 0.

| Event | Sex | Equipment | A | B | C |
|---|---|---|---|---|---|
| SBD | M | Raw | 1199.72839 | 1025.18162 | 0.009210 |
| SBD | M | Single | 1236.25115 | 1449.21864 | 0.01644 |
| SBD | F | Raw | 610.32796 | 1045.59282 | 0.03048 |
| SBD | F | Single | 758.63878 | 949.31382 | 0.02435 |
| B | M | Raw | 320.98041 | 281.40258 | 0.01008 |
| B | M | Single | 381.22073 | 733.79378 | 0.02398 |
| B | F | Raw | 142.40398 | 442.52671 | 0.04724 |
| B | F | Single | 221.82209 | 357.00377 | 0.02937 |

Published examples: Dmitry Inzarkin, 2019 IPF World Open Men's, M Single-ply SBD, 92.04 kg, total 1035 -> 112.85. Susanna Torronen, 2019 World Open Classic Bench, F Raw B, 70.50 kg, 122.5 -> 96.78. Source: IPF_GL_Coefficients-2020.pdf.

## Glossbrenner

Product number = lifter's total x Glossbrenner bodyweight coefficient. Used mostly by GPC affiliates; average of Schwartz/Malone and Wilks with a linear section for heavy lifters.

- Men: BW < 153.05: (Schwartz(BW) + WilksMen(BW)) / 2; else (Schwartz(BW) - 0.000821668402557*BW + 0.676940740094416) / 2.
- Women: BW < 106.3: (Malone(BW) + WilksWomen(BW)) / 2; else (Malone(BW) - 0.000313738002024*BW + 0.852664892884785) / 2.
- Wilks inside Glossbrenner applies its own clamps.

Schwartz (men), x = max(BW, 40):
- x <= 126: 6.31926 - 0.262349x + 0.511550e-2 x^2 - 0.519738e-4 x^3 + 0.267626e-6 x^4 - 0.540132e-9 x^5 - 0.728875e-13 x^6
- x <= 136: 0.5210 - 0.0012(x - 125); x <= 146: 0.5090 - 0.0011(x - 135); x <= 156: 0.4980 - 0.0010(x - 145); else 0.4879 - 0.0009(x - 155)

Malone (women): 106.011586323613 * max(BW, 29.24)^-1.293027130579051 + 0.322935585328304.

Schwartz and Malone are not spelled out in the source skill (it imports them from OpenPowerlifting's `schwartzmalone` module); the constants above reproduce the source's Glossbrenner test values exactly: men coef(100) = 0.5812707859533183, women coef(100) = 0.7152488066040259, glossbrenner(M, 100, 1000) = 581.27, glossbrenner(F, 60, 500) = 492.53032. The Schwartz piecewise tail above 126 kg is not covered by those tests.

Masters (age) handicaps such as the Glossbrenner age multipliers (ages 40-80, revised from seven years of lifter totals) are separate multipliers applied on top of the product number; they are not part of this pack.
