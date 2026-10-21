# transit-period-finder: sources, design, and drop log

## Provenance

Compiled (AIP 0.6a1) from five curated Agent Skills, copied here verbatim:

| Source | What it contributed |
|---|---|
| `light-curve-preprocessing/SKILL.md` | Quality-flag conventions, outlier sigma guide, flatten window guidance, pipeline order, sine-fitting caveat |
| `lomb-scargle-periodogram/SKILL.md` | Lomb-Scargle for the stellar-variability (rotation) period, harmonics/aliases, period ranges |
| `box-least-squares/SKILL.md` | BLS search, autoperiod/power grids, objectives, `compute_stats` vetting (odd/even, SNR, transit count), top-peak comparison, alias issues |
| `transit-least-squares/SKILL.md` | TLS usage, SDE/SNR thresholds, refinement window strategy, transit masking, multi-planet search, "transits without data" warning |
| `exoplanet-workflows/SKILL.md` | Overall pipeline stages, method selection, validation thresholds, expected depths and period ranges, best practices, common issues |

Target task (used to shape defaults and to functional-test): a TESS 2-minute light curve
(`time, normalized flux, quality flag, flux error`, `#` header lines) of a spotted star with a
hidden transiting planet; write the period, rounded to 5 decimals, to a text file. The
container has Python 3.12 with numpy 1.26, scipy 1.13, astropy 6.0, lightkurve 2.4,
transitleastsquares 1.32.

## Procedure and component-kind choices

| Step | Kind | Why |
|---|---|---|
| `inspect-light-curve` | execution | Parsing columns, counting flag values, per-subset scatter, cadence, gaps and the Lomb-Scargle rotation period are deterministic computations. |
| `choose-flag-convention` | decision (choice) | Which flag value means "good" is a judgment over the task text and subset statistics (the sources insist conventions vary and must be verified). Fixed label set, so a decision, not free text. |
| `detrend-and-search` | execution | Quality filter, Savitzky-Golay flatten, flare clipping, BLS search, peak de-duplication, vetting statistics and robustness re-runs are all numeric. |
| `vet-candidates` | decision (noul + 2 choices) | Whether a peak is a credible transit (SDE/SNR/transit count/duration/rotation harmonic/stability), which rank is the planet, and whether its period is an alias are judgments over the numbers with an answer space known in advance. The source thresholds are written into the instructions. |
| `route-on-detection` | router | Credible detection goes to scripted refinement; otherwise a hand investigation. |
| `refine-and-write` | execution | Masked re-flatten, fine BLS, trapezoid fit, transit-timing ephemeris, rounding and writing are deterministic. |
| `investigate-weak-signal` | client_task | When vetting fails, the next moves (other windows, durations, flag convention, TLS) depend on what the agent sees; it must still write a period. Template in `assets/investigate.md`, method detail in `references/methods.md`. |
| `end` | end | Result: the output path plus the candidate list and search record. |

### Method decisions (deviations from the sources, with reasons)

- **BLS is the scripted search; TLS is the manual fallback.** The sources rate TLS as more
  sensitive. Measured here, a TLS search over ~16.5k 2-minute points did not finish in 10
  minutes (multithreaded runs hung on this test machine), and even a +-2% window took 60 s
  single-threaded, with a coarser period (5.3570 +- 0.014 d) than BLS plus a fit. `aip run`
  kills scripts after 60 s. BLS on 10-minute bins searches 0.5 d to baseline/2 in a few
  seconds per window. TLS usage, parameters and thresholds are kept in `references/methods.md`
  for the fallback, and the SDE thresholds are applied to the BLS SDE.
- **Flatten first, then clip only upward outliers.** The sources say to remove outliers
  before flattening at sigma 3, and at sigma 5 after flattening. On a spotted star (4% p2p
  rotation amplitude here), a raw-flux 3-sigma clip removes rotation extrema, not outliers.
  lightkurve's `flatten` already sigma-clips (3 sigma, 3 iterations) when it fits the trend,
  which is the "outliers before trend removal" protection. After flattening only *upward*
  3-sigma points (flares) are clipped. A low-side clip at 3 to 5 sigma would delete transits
  deeper than 3 to 5 times the noise (e.g. hot Jupiters).
- **Window rule: P_rot/4 clipped to 0.25-0.75 d.** This follows "longer than the transit,
  shorter than the rotation period", made concrete. In testing, P_rot/3 with a 1-day cap let
  the P_rot/2 harmonic through as a long box "transit" on a 3.2-day rotator. The ~300-500
  cadence TESS rule of thumb from the source equals 0.4-0.7 d at 2-minute cadence, in the same
  range.
- **Refinement.** The sources say to refine with a narrow (+-2-10%) TLS re-search. Instead we
  mask the transits, re-flatten (unmasked flattening suppresses depth and biases the period),
  run a dense +-1% BLS grid, then a trapezoid least-squares fit, cross-checked against a linear
  fit to the individual transit times. On the task file these agree within 1e-5 d (fit
  5.35845 +- 0.00018 d, timing 5.35844 d).
- **Vetting statistics are computed after a local polish** of each coarse peak on unbinned
  data. Otherwise period error accumulated over many transits produces spurious odd/even
  mismatches; this happened on a 13-transit synthetic case. `odd_even_depth_ratio` is
  reported because a high mismatch *sigma* with both depths substantial comes from
  detrending under fast rotation, while a ratio near 0 is the 2x-alias signature.

## Functional test record

`aip run` with the task's file and the task statement: flag convention `zero_is_good`.
Search window 0.35 d (P_rot 1.40 d). Top candidate 5.3600 d: SDE 22.0, SNR 21.9, 4
transits, odd/even ratio 0.98, no secondary, stable across 0.21/0.52 d windows. The other
peaks are its 2x, 0.5x and 1.5x aliases. Output `5.35845`. Synthetic checks (scratch only):
an injected 3.77120 d planet on a 3.19 d rotator with 5% bad flags, NaNs and flares gave
3.77124. An injected 1.93055 d planet on a 0.85 d rotator gave 1.93054. A planet-free
rotator went down the `false` branch, where the fallback wrote a low-confidence value. Also
tested: the `double`/`half` alias factors, inverted flags (`nonzero_is_good`), and a
3-column CSV with a header row and un-normalised flux.

## Deliberate-drop log

Each source item not carried into the body, a script, the template, or `references/methods.md`:

| Source item | Where | Why dropped |
|---|---|---|
| `pip install ...` / Dependencies blocks | all five | Install steps don't apply: the container provides the packages, and `requires` declares what the scripts import. |
| Plotting snippets (`plt.plot`, `lc.plot()`, `pg.plot`), "visualize each step", "plot before and after", "visual inspection / phase-folded plots" | all five | The consumer is headless and autonomous. The checks a plot supports are computed instead: per-transit points and depths, odd/even depths and ratio, depth at phase 0.5, depth folded at P/2, multi-window stability, residual scatter. |
| Literature citations (Kovacs+2002, Hippke & Heller 2019, Hartman & Bakos 2016) and documentation / tutorial URLs, lightkurve tutorial section numbers | BLS, TLS, workflows, preprocessing, LS | Bibliographic; no actionable content. |
| Overview / introductory prose ("BLS models a transit as an upside-down top hat", "LS extends the classical periodogram to unevenly sampled data", "Preprocessing is essential...") | all five | Background the agent already knows; the actionable parts are in the steps. |
| "Document your workflow - reproducibility is key" | workflows | Covered structurally: every step returns its parameters (`search_summary`, `refine_summary`). |
| BLS/TLS pros and cons lists, "Try both and compare" | BLS, workflows, TLS | Folded into the method choice above and the fallback (TLS on demand). Running both on every run would exceed the 60 s script budget for no gain on a clear detection. |
| Habitable-zone period ranges (200-400 d Sun-like, 10-50 d M dwarf), warm planets 10-100 d | workflows | Kept as context in `references/methods.md`. A single-sector light curve cannot constrain periods above ~baseline/2, so they do not set defaults. |
| Manual median/std outlier recipe | preprocessing | Superseded by lightkurve's sigma clipping on the flattened flux (the same method, applied after detrending for the reason above). The sigma guide is kept in `references/methods.md`. |
| Iterative sine fitting as a detrender | preprocessing | Not used by the scripts: the source warns it removes periodic signals, and it needs many iterations for evolving spots. Kept in `references/methods.md` with the warning. |
| Lomb-Scargle `pg.model` fitting example | LS | Same as sine fitting; documented in the reference, not used by the scripts. |
