---
name: tess-transit-period
description: Find the orbital period of a transiting exoplanet hidden under stellar variability (starspot rotation, flares) in a TESS or Kepler light-curve text file. Filters quality flags and outliers, measures the rotation period with Lomb-Scargle, detrends with a Savitzky-Golay flatten (or iterative sine fitting), searches with Transit Least Squares, refines the period, cross-checks with Box Least Squares odd/even and P/2 / 2P alias tests plus a batman model fit, and writes the period rounded to 5 decimals.
compatibility: Python >= 3.10 with numpy, scipy, astropy, lightkurve, transitleastsquares (optional batman-package for the model-fit cross-check). All are preinstalled in the task container (python:3.12-slim + numpy 1.26.4, astropy 6.0.1, lightkurve 2.4.2, transitleastsquares 1.32, batman-package 2.5.2). No network needed.
---

# TESS Transit Period

## Trigger When

- A task gives a light curve (time, flux, quality flag, flux error) and asks for the period of a transiting exoplanet, e.g. "write the period to period.txt rounded to 5 decimals".
- The light curve shows strong stellar variability (rotational modulation, spots, flares) that hides shallow transit dips.
- You need to detrend a TESS/Kepler/K2 light curve without destroying transits, or choose between TLS, BLS and Lomb-Scargle.
- A transit search returned a suspicious period (half or double the truth, a rotation harmonic, a weak SDE) and needs validating.

## Purpose

Turns a raw, activity-dominated light curve into one validated orbital period. The skill carries the pipeline order (quality flags, then asymmetric clipping, then detrending, then a second clip, then search), the detrending window rule tied to the rotation period, a TLS broad-then-narrow search, and the validation rules that catch the usual wrong answers: P/2 and 2P aliases, peaks at rotation harmonics, inverted flag conventions, and weak detections. One script does the numerical work. You read its flags, answer one decision, and rerun with the matching option when a flag fires.

## Inputs and output

- Light curve: whitespace- or comma-separated text with `#` comment lines. Default columns: `time flux flag flux_err` (time in days: MJD/BTJD/BJD). Use `--cols t,f,q,e` (0-based, `-1` for absent) if the order differs. Missing or non-positive errors are filled from the point-to-point scatter.
- Output: the period file holds one number in days, rounded to 5 decimals (e.g. `2.44535`). The script writes it with `--out`.

## Procedure

Progress:
- [ ] 1. Check the environment
- [ ] 2. Inspect the file and answer `input_format`
- [ ] 3. Run the search
- [ ] 4. Answer `candidate_verdict` from the report
- [ ] 5. Act on the verdict (rerun if needed)
- [ ] 6. Write and verify the output file

### 1. Check the environment (execution)

Before the first script run, check that every package the script needs is importable. Name everything that's missing:

```bash
python -c "import numpy, scipy, astropy, lightkurve, transitleastsquares; print('ok')"
python -c "import batman" || echo "batman missing: model-fit cross-check will be skipped"
```

Do not pip-install anything in the task container. The required set is already there.

### 2. Inspect the input (decision)

Run `head -20 <lightcurve>`. Then compare the task statement with the file. Answer:

```yaml
input_format:
  column_order:
    type: choice
    instructions: Do the data columns match time, flux, flag, flux_err (the script default)?
    criteria:
      default: Columns are time, flux, flag, flux_err in that order (comments/task text confirm or don't contradict it).
      reordered: All four exist but in another order; pass --cols with the 0-based indices.
      missing_columns: No flag and/or no error column; pass -1 for it in --cols.
  flag_convention:
    type: choice
    instructions: Which flag value marks good data? Trust the task statement first; the script re-checks it.
    criteria:
      zero_good: Task or header says 0 = good (standard TESS/SPOC). Use --flag-good zero (default).
      nonzero_good: Task or header explicitly says 0 = bad / nonzero = good. Use --flag-good nonzero.
      no_flags: No flag column, or flags are meaningless. Use --flag-good all.
```

Getting the column order wrong is costly. Reconsider `reordered` vs `default` if the header comments are unclear.

### 3. Run the search (execution)

Run from the skill folder. Write reports to a scratch location, not into the skill folder:

```bash
python scripts/find_period.py /root/data/tess_lc.txt --out /root/period.txt --json /tmp/period_report.json
```

Expect about 25 s with 4 threads on 2-min cadence data. What the script does, in order:
1. Loads the file and keeps rows by `--flag-good` (default: flag == 0). It drops non-finite values, sorts by time and normalises to the median. If fewer than 50% of rows survive, it warns that the convention may be inverted and reports the point-to-point scatter of both flag groups.
2. Clips with `sigma_upper=3, sigma_lower=10`. Flares and cosmic rays are positive; transits are negative and must survive.
3. Runs Lomb-Scargle (astropy) on the cleaned flux. This gives the rotation period `P_rot` and its semi-amplitude.
4. Detrends. Default is lightkurve `flatten` (Savitzky-Golay, polyorder 2), with the window in days = `min(0.5, max(P_rot/3, 0.25))`, converted to an odd number of cadences. The window must be longer than the transit (~1–5 h) and shorter than the rotation period. If the residual scatter is still more than 1.5× the flux errors, it retries at 0.15 d and keeps that if the scatter drops. With `--detrend sine`, it instead divides out the strongest Lomb-Scargle sinusoid 50 times (periods > 0.25 d).
5. Clips again with `sigma_upper=3, sigma_lower=20`, then inflates `flux_err` so it matches the real residual scatter.
6. Runs a broad TLS search, `--period-min 0.5` to `--period-max` = span/2 (at least two transits). It lists the top distinct peaks. If the top peak is within 1% of a rotation harmonic (`P_rot/k` or `k·P_rot/2`), it moves to the strongest non-harmonic peak instead.
7. Refines with TLS over ±5% of the candidate, `oversampling_factor=10`. This refined period is the answer.
8. Checks aliases with BLS: a fine search at P/2, P and 2P, reporting depth SNR, odd and even depths, the odd–even difference in σ, and how many transit windows have data.
9. Fits a batman transit model (P, T0, Rp/Rs, a/Rs, b) as a precision cross-check.
10. Raises flags (rules below), applies `--force-factor` and writes the period to `--out`.

Flag rules (deterministic, in the script):

| Flag | Rule |
|---|---|
| weak / moderate | broad-search SDE < 6 (weak) or < 9 (moderate); refined SNR < 7 |
| odd/even mismatch | BLS odd vs even depth at P differ by > 3σ → true period may be 2P, or an eclipsing binary |
| P/2 | at P/2, both odd and even depths > 3σ, consistent within 3σ, depth SNR > 7 → true period may be P/2 |
| rotation harmonic | refined P within 1% of a rotation harmonic, or harmonic peaks were skipped / all top-30 are harmonics |
| BLS≠TLS | BLS and TLS periods differ by > 0.2% |
| model fit | batman P differs from TLS by > max(3σ_fit, TLS uncertainty) |
| one transit | fewer than 2 transit windows with data |
| gaps | TLS reports transit epochs inside data gaps (informational: one empty epoch in a gap is normal) |
| flag convention | < 50% of rows kept by the quality filter |

### 4. Judge the candidate (decision)

The input is the script's stdout JSON and stderr log (or the `--json` report). Answer:

```yaml
candidate_verdict:
  verdict:
    type: choice
    instructions: What should happen with the refined TLS period?
    criteria:
      accept: No flags, or only the informational "gaps" flag; or flags already resolved by an earlier rerun. Broad SDE >= 6, odd/even consistent at P.
      fix_flags: The "flag convention" flag fired, or the input_format answers were wrong. Rerun with corrected --flag-good / --cols.
      use_half: The "P/2" flag fired. P/2 shows real, equal-depth transits in both odd and even epochs, so P is a double.
      use_double: The "odd/even mismatch" flag fired at P (alternating deep/shallow events) and the mismatch at 2P is much smaller (consistent, or several times lower in sigma), with events at every 2P epoch.
      retry_detrend: The weak, rotation-harmonic, all-harmonic or BLS≠TLS flags fired (variability left over, or transits damaged).
      mask_and_research: A strong signal was found but it is not the planet asked for (e.g. an eclipsing binary flagged by odd/even mismatch, or a second planet is requested).
  is_planet_like:
    type: noul
    instructions: Is the accepted signal consistent with a planetary transit?
    criteria:
      true: Depth roughly 0.0001–0.03, duration short compared with the period, odd and even depths agree, more than one transit.
      false: Depth > 0.03, V-shaped / unequal alternating eclipses, or one event only.
```

Wrongly accepting an alias is the costly mistake. Reconsider any close call that leans toward `accept` when the P/2, odd/even or harmonic flags fired. Always choose the shortest period whose odd and even transits are both present and consistent. A 2P candidate whose half-phase epochs also hold transits is just P. Rule out `use_double` the same way: at P, odd and even depths agree and every epoch with data shows a dip.

### 5. Act on the verdict (execution)

- `accept`: done. The period file is already written.
- `fix_flags`: rerun with the corrected `--flag-good zero|nonzero|all` and/or `--cols`.
- `use_half` / `use_double`: rerun with `--force-factor 0.5` or `--force-factor 2`.
- `retry_detrend`: try these in order, keeping the `--out` of the best run only:
  1. `--detrend sine` (iterative sine fitting). It strips sinusoidal rotation without a sliding window but can also remove signal, so trust it only if it beats flatten.
  2. `--window-days 0.25` and `--window-days 0.75`, to bracket the default. Keep the window ≥ 3× the transit duration and < P_rot/2.
  3. Narrow the search with `--period-min/--period-max` if the task or physics constrains the period. Hot Jupiters run 0.5–10 d, warm planets 10–100 d, the M-dwarf habitable zone 10–50 d. The period can't exceed span/2 if two transits are needed.
  
  Pick the run with the highest broad SDE whose flags are clean. If two clean runs agree within the TLS `period_uncertainty`, either is fine. If every run is weak, report the best one anyway: the task needs a number. Say in the final message that the detection is weak.
- `mask_and_research`: rerun with `--mask P,T0,DURATION` (values from `tls_refined`, repeatable) to remove the found signal, then search again.

Run every rerun with the same launch command as step 3, plus the options.

### 6. Write and verify the output (execution)

```bash
cat /root/period.txt   # exactly one line, e.g. 5.35792
python -c "import re;s=open('/root/period.txt').read().strip();assert re.fullmatch(r'\d+\.\d{5}',s),s;print('format ok',s)"
```

## Gotchas

- Window length in `lc.flatten()` is in **cadences**, not days, and must be odd. 361 cadences is 0.5 d at 2-min cadence but 7.5 d at 30-min. The script converts from days.
- A window ≥ ~P_rot/2 leaves rotation residuals, and TLS/BLS then lock onto artefacts at long periods or rotation harmonics. A window shorter than ~3× the transit duration eats the transit. Use the rotation period from Lomb-Scargle to choose it.
- Don't sigma-clip symmetrically after flattening: 3σ low clipping deletes in-transit points. Clip flares on the high side only and keep a very loose low side.
- TLS needs `flux_err` as the third argument. With underestimated errors, odd/even σ values and SNR are inflated, which is why the script rescales them to the residual scatter.
- SDE from a narrow refinement window is meaningless, because it's normalised over the searched range. Judge strength by the broad-search SDE.
- astropy 6 `BoxLeastSquares.compute_stats()` has **no** `transit_count` key. Use `len(stats['transit_times'])` / `stats['per_transit_count']`. `depth`, `depth_odd` and `depth_even` are `(value, error)` tuples.
- Re-flattening with the transits masked (`flatten(mask=...)`) interpolates the steep spot trend under each transit and can fake odd/even mismatches on active stars. The script does not do it.
- TLS warning "X of Y transits without data. The true period may be twice the given period": check the 2P BLS line. One empty epoch inside the mid-sector gap is normal.
- The quality-flag convention varies by source. Trust the task statement, but if fewer than half the rows survive, compare both conventions (the script prints the scatter of each group).
- Lomb-Scargle finds rotation, not shallow transits. Use it only to measure `P_rot`, never as the transit period.

For method details (BLS/TLS/Lomb-Scargle APIs, result attributes, validation thresholds, transit depths by planet size, preprocessing parameters), read [references/methods.md](references/methods.md). It's for writing ad-hoc diagnostics or debugging a script failure.
