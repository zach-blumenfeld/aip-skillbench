# Method selection

TLS, BLS, and Lomb–Scargle solve different problems. Pick before you run.

## Transit Least Squares (TLS) — default for exoplanet transit detection

- Fits a limb-darkened transit template, not a box; most sensitive for
  shallow transits.
- Returns an SDE (signal-detection efficiency), SNR, depth, duration,
  mid-transit time, and transit count.
- Automatic period grid is dense near short periods; good baseline.
- Slower than BLS/LS on long time series — budget accordingly.
- Requires `flux_err`; `transitleastsquares` will refuse to run without
  it or will produce misleading weights.

## Box Least Squares (BLS) — astropy-native alternative

- Models the dip as a box (upside-down top-hat). Faster than TLS.
- Reports period, duration, depth, SNR via `compute_stats`, odd-even
  depth comparison, and transit count.
- Period-grid sensitive: use `autopower(duration)` for first-pass; use
  `power(periods, duration)` on a dense custom grid for refinement.
- Pick BLS when the user asks for astropy only, or when you need fine
  grid control.

## Lomb–Scargle (LS) — general-purpose periodicity

- Not transit-shaped: finds sinusoidal periodicity (rotation,
  pulsation, EB with sinusoidal flux variations).
- Use when the goal is "find the dominant period in this star's light
  curve" rather than "find a transiting planet".
- Reports period and false-alarm probability; no depth/duration.
- Fast — good first-pass if the signal shape is unknown.

## SDE / SNR / power thresholds

| Metric | Weak | Moderate | Strong |
| --- | --- | --- | --- |
| TLS SDE | < 6 | 6–9 | > 9 |
| TLS SNR | < 5 | 5–7 | > 7 |
| BLS SNR (depth / depth_err) | < 5 | 5–7 | > 7 |
| LS FAP | > 1e-2 | 1e-4 – 1e-2 | < 1e-4 |

These thresholds come straight from the TLS paper (Hippke & Heller 2019)
and the BLS/LS documentation; apply them in the `validate-detection`
decision.

## Aliases and harmonics

- TLS warns `X of Y transits without data` when gaps make the true
  period look doubled. Re-check at `2 * period` and `period / 2`.
- LS peaks at `P/2` and `2P` are common harmonics; the fundamental is
  usually the strongest, but check both when peaks are close in power.
- Odd-even depth mismatch > 3σ on BLS/TLS points to an eclipsing binary,
  not a planet.
