---
name: tess-exoplanet-period
description: Recover the orbital period of a transiting exoplanet from a TESS-style light curve where stellar activity (starspots, rotational modulation) is hiding the transit. Provides the filter → detrend → Box-Least-Squares → refine pipeline, parameter defaults that work on single-sector TESS data, and the single-number-rounded-to-N-decimals output format. Use when the task gives a 4-column light curve (time MJD, normalized flux, quality flag, flux uncertainty) and asks for the planet's orbital period written to a file.
compatibility: Requires Python 3.10+ with numpy, scipy, and astropy installed.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Recover the orbital period of a transiting exoplanet from a TESS-style
  light curve where stellar activity (rotation, starspots) dominates the
  raw flux variations. Provides the filter → detrend → BLS pipeline, the
  parameter defaults that work on single-sector TESS-cadence data, and
  the exact output format the benchmark expects (one float, fixed
  decimal precision, no units).

trigger_when:
  - Task asks to find or identify the orbital period of a transiting
    exoplanet from a light curve file.
  - Input is a TESS- or Kepler-style light curve with a time column
    (MJD or BJD), a normalized flux column, and usually a quality flag.
  - Raw light curve shows strong stellar variability (rotational
    modulation, starspots) that hides the transit signal.
  - The required output is a single period value rounded to a fixed
    decimal precision and written to a file (typical contract).

do_not_use_when:
  - The signal of interest is the stellar rotation or pulsation itself
    rather than a transiting planet (use Lomb-Scargle — BLS is for
    box-shaped dips, not sinusoids).
  - The light curve already shows clean, obvious transits and no
    detrending is required (a quick phase-folding script is faster).
  - The task asks for transit depth, duration, RV-derived mass, or other
    characterisation beyond the period — this skill stops at the period.

scope_and_approval: >
  Read-only on the input light curve. Writes exactly one file at the
  output path the task specifies (default `/root/period.txt`) containing
  one floating-point number with a trailing newline. Safe to run
  without approval — no side effects beyond that single file.

steps:
  - name: read-task-paths
    description: >
      Re-read the task instruction (do not assume defaults from this
      skill). Extract three values: the input light-curve path
      (commonly `/root/data/tess_lc.txt`), the output path (commonly
      `/root/period.txt`), and the required decimal precision (commonly
      5). The output format is one floating-point number, no units, no
      header.

  - name: inspect-lightcurve
    description: >
      Read the first ~10 lines of the input file before parsing to
      confirm the layout (whitespace- vs comma-separated, presence of a
      header line, column order). The standard layout from the task is
      4 whitespace-separated columns: time (MJD), normalized flux,
      quality flag, flux uncertainty.

  - name: load-and-filter
    description: >
      Load with `numpy.loadtxt` (or `pandas.read_csv` with
      `delim_whitespace=True` if a header is present). Keep only rows
      where quality flag is 0 (TESS convention: 0 = good). Drop NaN/inf
      in time, flux, or uncertainty. Sort by time. See
      [scripts/detect_period.py](scripts/detect_period.py) functions
      `load_lightcurve` and `quality_filter`.

  - name: detrend-stellar-activity
    description: >
      Divide out the slow stellar-activity envelope so the transit dips
      stand out. Default: Savitzky-Golay filter with a window of
      ~1.0 day (much larger than a typical 1–5 h transit, comparable to
      stellar rotation) and polyorder 3. Median filter is a robust
      fallback if Savitzky-Golay introduces ringing. Implemented as
      `detrend_savgol` in scripts/detect_period.py.

  - name: sigma-clip-outliers
    description: >
      Apply an *asymmetric* sigma clip to the detrended flux: tight
      upper threshold (~3σ) to remove flares and cosmic rays, loose
      lower threshold (~6σ) so transit dips are not clipped along with
      noise. `astropy.stats.sigma_clip` accepts separate sigma_lower
      and sigma_upper for this.

  - name: bls-periodogram
    description: >
      Run Box-Least-Squares with `astropy.timeseries.BoxLeastSquares`.
      Use `autopower` with durations 0.05–0.20 days (~1.2–4.8 h) and
      `frequency_factor=5` for a dense grid. Period range: minimum
      0.5 day, maximum `(t.max() - t.min()) / 2.5` so at least two
      transits fit in the baseline. Take the period at the peak power.

  - name: refine-peak
    description: >
      Re-evaluate BLS on a fine linear period grid (±1% around the
      coarse peak, ~10,000 trial periods). The refined value is what
      gets rounded and written. Without this step the autopower grid
      spacing is often coarser than the requested 5-decimal precision.

  - name: phase-fold-sanity-check
    description: >
      Phase-fold the detrended flux on the refined period. Confirm a
      single coherent dip near phase 0. If two equal dips appear per
      cycle, the true period is double — re-run with the doubled value
      as the coarse peak and refine again.

  - name: write-output
    description: >
      Write the refined period to the output path as `f"{period:.{N}f}\n"`
      where N is the task's decimal precision (default 5). One line, no
      header, no units, no scientific notation. The grader reads with
      something like `float(open(path).read().strip())`.

decisions:
  - signal: Quality column is absent or every row is non-zero.
    action: Skip the quality cut and rely on the asymmetric sigma-clip
      after detrending.
  - signal: BLS top peak sits at the grid edge (minimum or maximum
      period).
    action: The grid is biasing the answer. Widen the search range
      (smaller min_period, larger baseline_divisor) and re-run.
  - signal: BLS peaks of comparable power at P and 2P.
    action: Prefer the longer period — BLS commonly finds half-period
      doubles. Phase-fold at both and keep the one with one dip per
      cycle.
  - signal: Detrending kills the transits (no dip left in residuals).
    action: Increase `--window-days` to ≥2× the stellar rotation period,
      or switch to biweight / iterative transit-masking — see
      [references/detrending.md](references/detrending.md).
  - signal: Stellar variability still dominates after one detrend pass.
    action: Mask in-transit points from a first BLS pass, refit the
      trend on the out-of-transit baseline, then re-run BLS. The
      iterative recipe is in [references/detrending.md](references/detrending.md).
  - signal: scripts/detect_period.py is unavailable or imports fail.
    action: Re-implement the same pipeline inline — the function
      bodies in the script are short enough to inline; the procedural
      knowledge in this skill body is the source of truth, not the script.

anti_patterns:
  - Reporting the *stellar rotation* period (the loudest peak in the
    raw light curve or in a Lomb-Scargle of the raw data) instead of
    the transit period. Always detrend first.
  - Symmetric sigma-clipping the detrended flux — transits are real
    downward outliers and get erased. Clip upward outliers harder
    than downward.
  - Skipping the quality cut. TESS cadences flagged as bad are usually
    momentum-dump artefacts that look like transits to BLS.
  - Running BLS on un-normalized flux. BLS assumes flux ≈ 1 with small
    dips; un-normalized data inflates the noise model and washes out
    the peak.
  - Writing the period with units (`2.44535 d`), scientific notation
    (`2.44535e+00`), extra precision, or a header line. The grader
    does a strict numeric comparison on the rounded value.
  - Using Lomb-Scargle for the transit search. Lomb-Scargle finds
    sinusoids — it's the right tool for the stellar rotation but
    the wrong tool for box-shaped transit dips.
  - Hard-coding a max period without checking the baseline. A 27-day
    TESS sector caps the searchable period at ~13 d; asking for
    longer returns nonsense.
  - Trusting the BLS `autopower` peak directly to 5 decimals. The
    autopower grid step is typically ~10⁻³ d; refine on a fine
    linear grid before rounding.

scenarios:
  - need: Task instruction at /root/task says "lightcurve at
      /root/data/tess_lc.txt, write period to /root/period.txt rounded
      to 5 decimal places".
    context: Single-sector TESS data (~27-day baseline) with visible
      rotational modulation on a ~5-day timescale; a transit is
      suspected but not visible by eye in the raw flux.
    action: >
      python scripts/detect_period.py /root/data/tess_lc.txt
      /root/period.txt
    outcome: /root/period.txt contains one line, e.g. `2.44535\n`,
      matching the format the example in the instruction shows.
  - need: Same task, but after running the default pipeline the
      phase-folded light curve shows two unequal dips per cycle.
    context: BLS found half the true period — a common transit-doubling
      failure mode.
    action: Re-run the refinement around 2× the coarse peak; if power
      at 2P > power at P, write 2P (then re-round).
    outcome: Single coherent dip in the phase-fold; period written
      with corrected value.
  - need: Same task, but the BLS spectrum is dominated by stellar
      rotation harmonics and the highest peak is at the rotation
      period.
    context: The default 1-day Savitzky-Golay window was too narrow
      and left rotation power in the residuals.
    action: Re-run with `--window-days 2.0` (or the value suggested in
      references/detrending.md) and verify the new top peak is at a
      transit-like period.
    outcome: BLS spectrum is dominated by a narrow peak at the
      planet's period rather than at the rotation period.
```
