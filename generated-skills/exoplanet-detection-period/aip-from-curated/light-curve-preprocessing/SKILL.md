---
name: light-curve-preprocessing
description: Preprocessing and cleaning techniques for astronomical light curves. Use when preparing light curve data for period analysis, including outlier removal, trend removal, flattening, and handling data quality flags. Works with lightkurve and general time series data.
compatibility: Requires Python with lightkurve, numpy, matplotlib.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Clean a raw astronomical light curve so a downstream period search
  (BLS, TLS, Lomb-Scargle) operates on data free of bad cadences,
  outliers, and long-term trends — without erasing the very transit
  or period signal the search is meant to find. Encodes the canonical
  order (quality flags → outliers → detrend) and the parameter knobs
  most often miscalibrated against TESS/Kepler-style data.

trigger_when:
  - Preparing a TESS, Kepler, or K2 light curve for period analysis or transit detection.
  - Raw flux time series shows obvious outliers, instrumental drift, or stellar variability that may be hiding a planetary signal.
  - About to run a periodogram (BLS, TLS, Lomb-Scargle) on raw flux and need a cleaned input.
  - Light-curve columns include a quality flag and you are unsure which convention is in use.
  - User mentions flattening, sigma clipping, detrending, or quality flags on time-series flux data.

do_not_use_when:
  - Already-detrended flux (e.g., PDC-SAP or community-flattened) is available and visibly clean.
  - The science target IS the long-term trend or stellar variability — flattening would destroy the signal of interest.
  - Hunting for shallow, long-duration signals where Savitzky-Golay smoothing would suppress the feature; choose a method that preserves them.

scope_and_approval: >
  Read-only on the input light curve. Writes only the cleaned output and
  optional plot to paths the agent specifies. No network. No destructive
  edits to the source file. Safe to run without checkpointing.

steps:
  - name: inspect-input
    description: >
      Open the input file. Confirm column order (typical TESS export:
      time, flux, flag, error), delimiter, time units (MJD vs. BJD vs.
      BKJD), and a sample of flag values. CRITICALLY, decide the flag
      convention before filtering — `good_is_zero` (standard TESS/Kepler)
      vs. `bad_is_zero` (some exported files invert it). If unsure, try
      both and pick the one that yields a cleaner light curve under
      visual inspection.
    outputs:
      - name: input-spec
        type: object
        description: Path, delimiter, column order, flag convention, cadence, time span.

  - name: choose-parameters
    description: >
      Pick preprocessing parameters from the input spec and target science.
      Defaults that work for TESS transit detection — sigma=3 for clipping,
      lightkurve default window for flatten(). Lower sigma (2–3) clips
      aggressively; higher (5–7) is conservative. Flatten window length
      must be LONGER than the expected transit duration but SHORTER than
      the stellar rotation period: 100–200 cadences for short trends,
      300–500 typical TESS, 500–1000 for long trends. If the downstream
      search handles trends itself (e.g., some BLS pipelines) consider
      --skip-flatten.
    inputs:
      - name: input-spec
        type: object
    outputs:
      - name: params
        type: object
        description: sigma, window_length (None for default), flag_convention, skip_flatten, skip_outlier_removal.

  - name: run-pipeline
    description: >
      Run the canonical pipeline in fixed order — quality flag filter,
      then sigma-clip outliers, then flatten (Savitzky-Golay). The order
      is non-negotiable: flags first removes garbage rows, outliers next
      stops bad points from biasing the trend fit, flatten last preserves
      transit-shaped dips while removing low-frequency variability.
    script: scripts/preprocess.py
    inputs:
      - name: input-spec
        type: object
      - name: params
        type: object
    outputs:
      - name: cleaned-lc-path
        type: string
        description: Path to .npz containing arrays time, flux, flux_err.

  - name: visual-check
    description: >
      Plot the cleaned curve. Confirm three things — outliers gone,
      long-term trend removed, transit-shaped dips still visible. If
      the dip you are after has been smoothed flat, the window is too
      short; revisit `choose-parameters` and re-run. Plot before and
      after each major step for fragile cases.
    script: scripts/plot_lc.py
    depends_on: [run-pipeline]
    inputs:
      - name: cleaned-lc-path
        type: string
    outputs:
      - name: plot-path
        type: string

  - name: optional-sine-detrend
    description: >
      ONLY when narrowband stellar variability (rotation, pulsation)
      remains after flatten() AND the transit you are searching for is
      deep enough to survive iterative periodogram subtraction. This is
      destructive to ANY periodic signal — usually the wrong choice
      ahead of a periodogram-based transit search. Skip by default.
    script: scripts/sine_fit_detrend.py
    depends_on: [run-pipeline]
    inputs:
      - name: cleaned-lc-path
        type: string
    outputs:
      - name: detrended-lc-path
        type: string

  - name: optional-second-pass
    description: >
      Re-run `scripts/preprocess.py` on the detrended output with
      --skip-flatten and a fresh sigma to remove residual outliers
      exposed by trend removal. Useful when the visual check shows
      a few new spikes after flatten(); skip otherwise.
    depends_on: [run-pipeline]
    inputs:
      - name: cleaned-lc-path
        type: string
    outputs:
      - name: cleaned-lc-path
        type: string
        description: Overwritten / new path holding the twice-clipped curve.

modes:
  - name: tess-transit-default
    body: >
      Standard recipe for TESS transit detection — flag_convention=good_is_zero,
      sigma=3, window_length default, no sine-fit detrend, no second pass.
      Matches the canonical pipeline that feeds BLS / TLS searches and is
      the right first attempt for almost every TESS task.
  - name: aggressive-clean
    body: >
      Stellar variability is loud and a vanilla flatten() isn't enough.
      Run `tess-transit-default` first, then `optional-second-pass` with
      sigma=2.5–3, then re-visual-check. Use `optional-sine-detrend` only
      if the periodogram is still dominated by stellar peaks AND you are
      confident the planet signal will survive subtraction.
  - name: minimal
    body: >
      Downstream search handles outliers and trends itself (e.g., a TLS
      pipeline with its own detrending). Run preprocess.py with
      --skip-outlier-removal and --skip-flatten to apply just the quality
      flag filter, preserving everything else.

search_shortcuts:
  - category: Libraries
    body: >
      lightkurve (LightCurve, remove_outliers, flatten, to_periodogram);
      numpy (np.loadtxt, np.median, np.std); matplotlib for plots.
  - category: Reference docs
    body: >
      https://lightkurve.github.io/lightkurve/tutorials/index.html ;
      https://lightkurve.github.io/lightkurve/tutorials/2.3-removing-noise.html

integrations:
  - partner: box-least-squares
    body: >
      Feed `cleaned-lc-path` directly into BLS as time / flux / flux_err.
      Keep flux_err — BLS uses it for proper weighting.
  - partner: transit-least-squares
    body: >
      TLS expects time, flux, flux_err arrays. The .npz from preprocess.py
      is a direct match: `np.load(path)["time"|"flux"|"flux_err"]`.
  - partner: lomb-scargle-periodogram
    body: >
      Lomb-Scargle is sensitive to outliers and trends; ALWAYS preprocess
      first. If hunting stellar rotation rather than transits, use
      `minimal` mode so flatten() doesn't erase the long-period signal.
  - partner: exoplanet-workflows
    body: >
      This skill is the cleaning stage of an end-to-end exoplanet
      pipeline: light-curve-preprocessing → BLS or TLS → period refinement.

scenarios:
  - need: >
      TESS light curve at /root/data/tess_lc.txt with 4 whitespace-separated
      columns (MJD time, normalized flux, quality flag, flux uncertainty).
      Strong stellar rotational modulation is hiding a transit signal; find
      the planet period.
    context: >
      flag column contains 0s and a few non-zeros — standard TESS convention,
      so good_is_zero applies. Time span on the order of one TESS sector.
    action: >
      `python scripts/preprocess.py /root/data/tess_lc.txt --output
      /tmp/lc_clean.npz --delimiter " " --flag-convention good_is_zero
      --sigma 3`. Hand `/tmp/lc_clean.npz` to a TLS search via
      `np.load(...)["time"|"flux"|"flux_err"]`.
    outcome: >
      Cleaned light curve with stellar variability flattened and outliers
      removed; downstream TLS recovers the planet period without false
      peaks from rotation.
  - need: >
      Long-cadence Kepler light curve with strong cosmic-ray spikes after
      the first detrending pass.
    context: >
      Visual check after first pass shows clean baseline with residual
      spikes above 3-sigma.
    action: >
      Re-run preprocess.py with --skip-flatten and --sigma 2.5 on the
      already-flattened output (the `optional-second-pass` step).
    outcome: >
      Residual spikes removed; trend is unchanged (flatten skipped).
  - need: >
      A community-exported light curve where the quality flag column uses
      the inverted convention (0 = bad, nonzero = good).
    context: >
      Standard good_is_zero run drops almost every cadence. Visual check
      of raw flag values shows mostly zeros.
    action: >
      Re-run with `--flag-convention bad_is_zero`.
    outcome: >
      Sensible number of cadences kept; downstream pipeline behaves as
      expected.

anti_patterns:
  - Reordering the pipeline (e.g., flattening before outlier removal). Outliers bias the trend fit; flag-flagged garbage rows poison both.
  - Filtering quality flags with the wrong convention. If almost all cadences disappear or the curve looks worse than raw, you are inverted — flip to `bad_is_zero` (or vice versa).
  - Dropping `flux_err`. BLS / TLS / Lomb-Scargle all use it for weighting; losing it degrades the period estimate.
  - Picking a flatten window shorter than the transit duration. The Savitzky-Golay filter will smooth the transit flat and the search will find nothing.
  - Using `sine_fit_detrend.py` ahead of a periodogram transit search. The iterative sine subtraction is destructive to ALL periodic signals — including the planet you are after.
  - Stacking sigma clips at sigma<2 hoping the curve gets "cleaner". You are deleting real data and biasing the noise floor.
  - Skipping the visual check. Plotting before/after each stage is the only cheap way to catch "flatten ate my transit" or "wrong flag convention".
  - Re-implementing outlier rejection / detrending by hand when `lightkurve.remove_outliers()` and `LightCurve.flatten()` already do it correctly and consistently.
```
