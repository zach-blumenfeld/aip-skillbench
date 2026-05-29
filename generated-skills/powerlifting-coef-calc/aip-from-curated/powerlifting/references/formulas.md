# Powerlifting score-normalization — formula reference

Each system maps `(sex, bodyweight_kg, total_kg [, equipment, event])` to a
single "points" number that lets lifters in different bodyweights (and
sometimes sexes) be compared on one scale.

`scripts/score.py` and `scripts/excel_formula.py` are the source of truth for
runnable math. This file is the human-readable reference and includes the one
system (Glossbrenner) the scripts do not implement.

---

## Dots — "Dynamic Objective Team Scoring"

Used by most modern non-IPF federations. Author: Tim Konertz (BVDK).

```
points = total_kg * (500 / poly(bw_kg))
poly(bw) = a*bw^4 + b*bw^3 + c*bw^2 + d*bw + e
```

Coefficients and bodyweight clamps:

| sex | a              | b             | c              | d           | e          | bw clamp     |
|-----|----------------|---------------|----------------|-------------|------------|--------------|
| M   | −1.0930e−06    | 7.391293e−04  | −0.1918759221  | 24.0900756  | −307.75076 | [40, 210] kg |
| F   | −1.0706e−06    | 5.158568e−04  | −0.1126655495  | 13.6175032  | −57.96288  | [40, 150] kg |

`Mx` lifters use the male table. Bodyweights outside the clamp are pinned to the
boundary. Zero bodyweight or zero total ⇒ 0 points.

Source: [powerliftpro](https://powerliftpro.app/understanding-the-dots-score-in-powerlifting-a-comprehensive-guide/),
OpenPowerlifting `crates/coefficients/src/dots.rs`.

---

## IPF GoodLift Coefficient (IPF GL)

The IPF's current official scoring (replaced the older IPF Points). Depends on
sex, equipment category, and event (full power vs bench-only).

```
points = total_kg * max(0, 100 / (A - B * exp(-C * bw_kg)))
```

Parameter table `(A, B, C)`:

| sex | equipment | event | A           | B           | C        |
|-----|-----------|-------|-------------|-------------|----------|
| M   | Raw       | SBD   | 1199.72839  | 1025.18162  | 0.009210 |
| M   | Single    | SBD   | 1236.25115  | 1449.21864  | 0.01644  |
| F   | Raw       | SBD   |  610.32796  | 1045.59282  | 0.03048  |
| F   | Single    | SBD   |  758.63878  |  949.31382  | 0.02435  |
| M   | Raw       | B     |  320.98041  |  281.40258  | 0.01008  |
| M   | Single    | B     |  381.22073  |  733.79378  | 0.02398  |
| F   | Raw       | B     |  142.40398  |  442.52671  | 0.04724  |
| F   | Single    | B     |  221.82209  |  357.00377  | 0.02937  |

Equipment grouping: `Raw`/`Wraps`/`Straps` → Raw row; `Single-ply`/`Multi-ply`/
`Unlimited` → Single-ply row. `Mx` uses the male rows. Events: `SBD` = full
powerlifting; `B` = bench-only. Undefined event/equipment combinations (`S`,
`D`, `SD`, `BD`) return 0.

`bodyweight_kg < 35` returns 0. Negative `100/denom` is clamped to 0.

Published reference values (used as smoke tests in `score.py`):
- Dmitry Inzarkin, 92.04 kg / 1035 kg / M / Single / SBD → 112.85
- Susanna Torronen, 70.50 kg / 122.5 kg / F / Raw / B → 96.78

Source: [IPF GL PDF](https://www.powerlifting.sport/fileadmin/ipf/data/ipf-formula/IPF_GL_Coefficients-2020.pdf),
OpenPowerlifting `crates/coefficients/src/goodlift.rs`.

---

## Wilks

Legacy formula still common in older datasets and some non-IPF federations.

```
points = total_kg * (500 / poly(bw_kg))
poly(bw) = a + b*bw + c*bw^2 + d*bw^3 + e*bw^4 + f*bw^5
```

| sex | a              | b              | c             | d              | e             | f             | bw clamp        |
|-----|----------------|----------------|---------------|----------------|---------------|---------------|------------------|
| M   | −216.0475144   |  16.2606339    | −0.002388645  | −0.00113732    | 7.01863e−06   | −1.291e−08    | [40, 201.9] kg   |
| F   |  594.31747776  | −27.23842536   |  0.82112227   | −0.00930733913 | 4.731582e−05  | −9.054e−08    | [26.51, 154.53]  |

`Mx` uses the male polynomial. Bodyweights outside the clamp pin to the
boundary (the upper bound avoids the polynomial's asymptote; the lower bound
avoids degenerate child-lifter coefficients).

Reference checks (verbatim from the OpenPowerlifting Python port):
- `wilks_coefficient_men(100)` = 0.6085890719066511
- `wilks_coefficient_women(100)` = 0.8325833167368228
- `wilks(M, 100, 1000)` ≈ 608.58907
- `wilks(F, 60, 500)` ≈ 557.4434

Source: [Wikipedia](https://en.wikipedia.org/wiki/Wilks_coefficient),
OpenPowerlifting `crates/coefficients/src/wilks.rs`.

---

## Glossbrenner *(not implemented in scripts)*

GPC-affiliate formula. Defined piecewise as an average of Schwartz/Malone and
Wilks:

```
men, bw < 153.05:   gloss(bw) = (schwartz(bw) + wilks_men(bw)) / 2
men, bw >= 153.05:  gloss(bw) = (schwartz(bw) + (A*bw + B)) / 2
                    with A = -8.21668402557e-4, B = 0.676940740094416
women, bw < 106.3:  gloss(bw) = (malone(bw) + wilks_women(bw)) / 2
women, bw >= 106.3: gloss(bw) = (malone(bw) + (A*bw + B)) / 2
                    with A = -3.13738002024e-4, B = 0.852664892884785

points = total_kg * gloss(bw_kg)
```

**Why not in `score.py`:** the Schwartz and Malone coefficients live in a sibling
OpenPowerlifting module that was not included in the curated source SKILL.md.
Reference values (Python port, for future verification once Schwartz/Malone are
sourced):
- `glossbrenner_coefficient_men(100)`  = 0.5812707859533183
- `glossbrenner_coefficient_women(100)`= 0.7152488066040259
- `glossbrenner(M, 100, 1000)` ≈ 581.27
- `glossbrenner(F, 60, 500)`   ≈ 492.53032

Source: [worldpowerliftingcongress.com Glossbrenner page](https://worldpowerliftingcongress.com/wp-content/uploads/2015/02/Glossbrenner.htm),
OpenPowerlifting `crates/coefficients/src/glossbrenner.rs`.

---

## Cross-system invariants

- **Inputs:** bodyweight and total are in **kilograms**. Convert pounds first.
- **Total = squat + bench + deadlift**, taking the *Best3* for each lift.
  If any lift was failed, the lifter has no total (skip the row).
- **`Mx` → male coefficients** across every system.
- **Zero bodyweight or zero total ⇒ 0 points** by convention. Treat zero
  bodyweight as "unknown".
- **Rounding:** OpenPowerlifting / OpenIPF spreadsheets report 3 decimals;
  IPF GL is often shown to 2. Apply `ROUND` *inside* spreadsheet formulas so
  downstream tolerance checks see the rounded value.
