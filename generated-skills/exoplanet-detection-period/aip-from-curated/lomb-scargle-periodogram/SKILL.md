---
name: lomb-scargle-periodogram
description: Lomb-Scargle periodogram for finding periodic signals in unevenly sampled time series data. Use when analyzing light curves, radial velocity data, or any astronomical time series to detect periodic variations. Works for stellar rotation, pulsation, eclipsing binaries, and general periodic phenomena. Based on lightkurve library.
compatibility: Requires Python with `lightkurve`, `numpy`, and `matplotlib` installed.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Find the strongest periodic signal in an unevenly sampled astronomical time
  series (light curves from Kepler/K2/TESS, radial velocity series) using the
  Lomb-Scargle periodogram via the `lightkurve` library. Handles uneven sampling
  that would break a classical FFT, returns the period at maximum power, and
  surfaces the top peaks so the agent can reason about harmonics and aliases.

trigger_when:
  - Searching for the dominant period in an unevenly sampled light curve.
  - Measuring stellar rotation, pulsation, or eclipsing-binary periods.
  - Running an initial period search before a more sensitive transit method (TLS, BLS).
  - User mentions "Lomb-Scargle", "periodogram", or asks for the period of a light curve.

do_not_use_when:
  - The science goal is exoplanet *transit* detection — prefer Transit Least Squares (TLS); it is shape-aware and more sensitive than Lomb-Scargle for box-shaped transits.
  - The light curve is dominated by stellar variability that hides the signal of interest — first flatten/detrend with `light-curve-preprocessing`, then run this skill on the residuals.
  - Data is evenly sampled with no gaps — a classical FFT (`numpy.fft`) is simpler and faster.

steps:
  - name: load-light-curve
    description: >
      Build a `lightkurve.LightCurve(time=..., flux=..., flux_err=...)` object from
      the cleaned time series. Quality-flag filtering, sigma-clipping, and detrending
      belong to `light-curve-preprocessing` — run that first if the signal is buried.
    outputs:
      - name: lc
        type: object
        description: lightkurve.LightCurve instance.

  - name: select-period-range
    description: >
      Pick `minimum_period` and `maximum_period` (days) from the science case. See
      `search_shortcuts` for typical ranges. Narrowing the range improves resolution
      and rules out aliases; widening it is appropriate when the period is unknown.
    inputs:
      - name: science_case
        type: string
        description: One of stellar-rotation, exoplanet-transit, eclipsing-binary, stellar-pulsation, or other.
    outputs:
      - name: minimum_period
        type: float
        nullable: true
      - name: maximum_period
        type: float
        nullable: true

  - name: compute-periodogram
    description: Run Lomb-Scargle over the chosen period range; return strongest period, max power, and the top peaks (for harmonic/alias inspection).
    script: scripts/run_lomb_scargle.py
    inputs:
      - name: data_path
        type: string
        description: Path to the light curve file (whitespace-delimited columns).
      - name: minimum_period
        type: float
        nullable: true
      - name: maximum_period
        type: float
        nullable: true
      - name: flag_col
        type: integer
        nullable: true
        description: Optional column index for a quality flag; rows with flag != 0 are dropped.
    outputs:
      - name: strongest_period_days
        type: float
      - name: max_power
        type: float
      - name: top_peaks
        type: list[object]
        description: Up to N (period_days, power) pairs at local maxima, strongest first.

  - name: interpret-peaks
    description: >
      Look at `top_peaks`. A single dominant peak well above the rest is likely the
      true period. Peaks at integer ratios of the strongest (period/2, period*2,
      period/3) are harmonics — the fundamental is usually the *longest* of the
      set. Very short periods close to the Nyquist limit, or near 1 day / 1 year,
      are likely aliases of the sampling cadence.
    inputs:
      - name: top_peaks
        type: list[object]
    outputs:
      - name: confirmed_period_days
        type: float

  - name: plot-periodogram
    description: >
      Optional. Call `pg.plot(view='period')` — pass `view='period'` explicitly;
      the default view is frequency and will mislead readers expecting period on
      the x-axis. Label axes ('Period [days]', 'Power').
    inputs:
      - name: periodogram
        type: object

  - name: fit-sinusoidal-model
    description: >
      Optional. `pg.model(time=lc.time, frequency=pg.frequency_at_max_power)`
      returns a sinusoidal model evaluated at the data times — overplot against
      the light curve as a visual sanity check.
    inputs:
      - name: periodogram
        type: object
      - name: confirmed_period_days
        type: float

search_shortcuts:
  - category: Stellar rotation
    body: "0.1 – 100 days (typical surface-feature modulation timescales)."
  - category: Exoplanet transits
    body: "0.5 – 50 days (most common; see TLS for sensitive transit search)."
  - category: Eclipsing binaries
    body: "0.1 – 100 days."
  - category: Stellar pulsations
    body: "0.001 – 1 day (high-frequency oscillations)."

integrations:
  - partner: light-curve-preprocessing
    body: >
      Runs *before* this skill. Drops bad-quality flags, removes outliers (3σ
      clip), and flattens (detrends) the light curve. When stellar activity
      dominates and hides the target signal, the periodogram on raw data finds
      the activity period — run on the flattened residuals to surface the buried
      planet/transit signal.
  - partner: transit-least-squares
    body: >
      Runs *after* this skill for exoplanet-transit work. Lomb-Scargle gives a
      first-pass period estimate; TLS refines it and is more sensitive to the
      characteristic box shape of a transit. A common pattern: LS finds the
      stellar rotation period; flatten removes it; TLS finds the planet.
  - partner: box-least-squares
    body: >
      Alternative to TLS for transit detection — older method, less sensitive
      but widely available in legacy pipelines.
  - partner: exoplanet-workflows
    body: >
      The umbrella playbook orchestrating preprocessing → LS → flatten → TLS for
      end-to-end exoplanet period detection from a raw light curve.

scenarios:
  - need: Find the rotation period of a Kepler target star.
    action: >
      Build LightCurve, run `scripts/run_lomb_scargle.py --data <path>
      --min-period 0.1 --max-period 100`. Take `strongest_period_days`.
    outcome: Dominant peak in the stellar-rotation band.
  - need: Find the orbital period of a transiting exoplanet whose signal is buried under stellar activity.
    context: Raw light curve shows strong, low-frequency variability.
    action: >
      Preprocess with `light-curve-preprocessing` (quality cut, 3σ clip, flatten).
      Run Lomb-Scargle on the flattened light curve as a first pass.
      Then run `transit-least-squares` over a narrow range around the LS peak
      to refine.
    outcome: LS surfaces a candidate transit period; TLS confirms and refines it.
  - need: Distinguish a true period from its first harmonic.
    context: top_peaks shows powers of comparable magnitude at P and 2P.
    action: >
      Phase-fold the light curve at each candidate. The fold that produces a
      single coherent shape is the fundamental; the one that produces two
      identical features per cycle is the harmonic.
    outcome: Fundamental period selected with empirical justification.

anti_patterns:
  - Plotting the periodogram without passing `view='period'` and then reading periods off a frequency axis.
  - Reporting the highest peak as the period when an integer-ratio harmonic sits beside it at comparable power — verify with phase-folding before committing.
  - Running Lomb-Scargle on a light curve dominated by stellar activity and reporting the activity period as the "period" of the target signal.
  - Skipping `light-curve-preprocessing` (quality cuts, outlier removal, flattening) before period search on a noisy or activity-contaminated light curve.
  - Using Lomb-Scargle as the primary tool for exoplanet *transit* detection — prefer TLS.
  - Treating very short periods (near the sampling cadence) or near 1 day / 1 year as physical without ruling out aliasing.
```
