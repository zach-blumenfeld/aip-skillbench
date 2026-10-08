# Validating a candidate and fixing common failures

Load this when the candidate is weak, the period looks like an alias, odd/even depths
disagree, or the answer changes with preprocessing.

## Thresholds

- TLS SDE > 9 very strong; SDE > 6 strong; SDE < 6 weak, may be a false positive.
- SNR > 7 reliable (TLS snr or BLS depth SNR); below 7 needs extra validation.
- Odd-even: depths differing by > 3 sigma means probably not a planet (eclipsing
  binary, or the true period is 2P) or an instrumental artifact.
- More transits observed = more confidence; need at least 2 with data.
- Duration must be reasonable for the orbit (not too long or short for P).

## How to validate

Signal-strength metrics against the thresholds; visual inspection of the
phase-folded data at the candidate period (and at 2P and P/2); odd-even consistency;
number of transits.

## Expected transit depths

Hot Jupiters 0.01-0.03 (1-3%); super-Earths 0.001-0.003; Earth-sized 0.0001-0.001.
Detection difficulty rises steeply for small planets. A measured depth far below the
expected one after flattening suggests the detrending window is eating the transit.

## Issue: no significant detection (low SDE, no clear peak)

- Preprocessing may be removing the signal: less aggressive outlier removal (higher
  sigma), less aggressive flattening (longer window).
- Data gaps during transits; check raw data for visible dips.
- Period outside the search range: extend it. BLS: try a wider duration range.
- The signal may simply be too shallow.

## Issue: period is 2x or 0.5x the expected one

Causes: aliasing from data gaps; missing alternate transits; TLS warning "X of Y
transits without data". Fix: check both periods manually; compare phase-folds at P,
2P, P/2; compare SDE at both; check odd-even (a mismatch at P supports 2P).
- Choose 2P when odd and even depths differ significantly, or the folded curve at 2P
  shows the alternate events are absent or different.
- Choose P/2 when a dip of comparable depth sits at phase 0.5 of the fold at P, and
  P/2 has strong power with a clean single transit when folded.
- Otherwise keep P.

## Issue: high odd-even mismatch

Not a planetary transit: eclipsing binary (true period 2P, primary and secondary
eclipses) or an instrumental artifact. Compare `depth_odd` vs `depth_even`.
Red noise and detrending residuals inflate apparent mismatches; the pack's errors
already include per-transit scatter and a red-noise beta.

## Issue: results vary with preprocessing

Compare results with different preprocessing, plot each step, make sure nothing is
over-smoothed. Prefer the setting that gives a consistent period with the highest
broad-search SDE and an undistorted transit shape.

## Issue: "flux_err required"

TLS needs flux uncertainties to weight points; pass them as the third argument. If the
file has none, use the point-to-point scatter as a constant error (the pack does).

## Best practices

1. Always include flux uncertainties. 2. Visualize each preprocessing step.
3. Check the quality-flag convention. 4. Sigma 3 for initial outliers, 5 after flattening.
5. Refine promising candidates with a narrow search. 6. Validate (SDE, SNR, folds).
7. Consider data gaps (aliasing). 8. Document the workflow for reproducibility.
