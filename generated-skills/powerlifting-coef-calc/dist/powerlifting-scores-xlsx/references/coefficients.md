# Powerlifting score formulas (OpenPowerlifting implementations)

All are encoded in `scripts/score_sheet.py` (Excel formulas + Python reference). Read this
file when you need to explain a value, hand-check a row, or the task asks for a score the
script does not build (Glossbrenner).

General rules shared by Dots, Wilks, Glossbrenner:
- Sex `M` and `Mx` use the men's coefficients; `F` uses the women's.
- Bodyweight 0/unknown or total 0 → points = 0.
- Points = coefficient × TotalKg. TotalKg = Best3Squat + Best3Bench + Best3Deadlift
  (only the lifts in the event; blank lifts are absent, not zero-failures).
- Data semantics (`data-readme.md`): a negative Best3 value means the lifter attempted
  that weight and failed; a failed lift means no total (TotalKg empty) → treated as 0 here.

## Dots (Dynamic Objective Team Scoring, BVDK / Tim Konertz)

coef = 500 / (A·x⁴ + B·x³ + C·x² + D·x + E), x = bodyweight clamped to the bounds.

| | A | B | C | D | E | clamp |
|---|---|---|---|---|---|---|
| Men (M, Mx) | -0.0000010930 | 0.0007391293 | -0.1918759221 | 24.0900756 | -307.75076 | [40, 210] |
| Women (F) | -0.0000010706 | 0.0005158568 | -0.1126655495 | 13.6175032 | -57.96288 | [40, 150] |

Bodyweights out of range use the boundary value. Hand-check: men 100 kg → coef 0.61552;
women 60 kg → coef 1.10855.

## Wilks

coef = 500 / (a + b·x + c·x² + d·x³ + e·x⁴ + f·x⁵) (note: polynomial written low→high).

| | a | b | c | d | e | f | clamp |
|---|---|---|---|---|---|---|---|
| Men | -216.0475144 | 16.2606339 | -0.002388645 | -0.00113732 | 7.01863e-06 | -1.291e-08 | [40, 201.9] |
| Women | 594.31747775582 | -27.23842536447 | 0.82112226871 | -0.00930733913 | 4.731582e-05 | -9.054e-08 | [26.51, 154.53] |

Upper bound avoids the asymptote; lower bound avoids huge coefficients for children.
Fixtures: coef men(100) = 0.6085890719066511, women(100) = 0.8325833167368228;
M 100 kg / 1000 kg → 608.58907; F 60 kg / 500 kg → 557.4434.

## IPF GOODLIFT (IPF GL, 2020)

points = total × max(0, 100 / (A − B·e^(−C·bodyweight)))

Equipment mapping: Raw, Wraps, Straps → Raw ("Classic"); Single-ply, Multi-ply,
Unlimited → Single ("Equipped"). Sex: M, Mx → M. Only events SBD and B are defined.

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

Undefined combination (other events), bodyweight < 35 kg, total 0, or a zero denominator
→ 0. Fixtures: M Single-ply SBD 92.04 kg / 1035 → 112.85; F Raw B 70.50 kg / 122.5 → 96.78.

## Glossbrenner (most often used by GPC affiliates; not built by the script)

points = total × GBC. GBC is the average of Schwartz/Malone and Wilks, piecewise:
- Men: bw < 153.05 → (schwartz(bw) + wilks_men(bw)) / 2; else
  (schwartz(bw) + (−0.000821668402557·bw + 0.676940740094416)) / 2
- Women: bw < 106.3 → (malone(bw) + wilks_women(bw)) / 2; else
  (malone(bw) + (−0.000313738002024·bw + 0.852664892884785)) / 2

The Schwartz and Malone coefficients are not included in the source material. If a task
needs Glossbrenner, obtain them first. Fixtures: coef men(100) = 0.5812707859533183,
women(100) = 0.7152488066040259; M 100/1000 → 581.27; F 60/500 → 492.53032;
bodyweight 0 → 0. Masters age multipliers (ages 40–80) are a separate handicap table,
also not in the source.
