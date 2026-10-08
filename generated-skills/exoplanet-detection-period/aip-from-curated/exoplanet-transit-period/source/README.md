# Source and compilation notes: exoplanet-transit-period

## Provenance

Compiled on 2026-10-08 from five curated Agent Skills, copied verbatim into this folder:

| Source | Role in the compiled skill |
|---|---|
| `exoplanet-workflows/SKILL.md` | Pipeline skeleton (load, QC, preprocess, search, validate, refine), method choice, validation thresholds, period ranges, expected depths, common issues |
| `light-curve-preprocessing/SKILL.md` | Quality-flag conventions, outlier sigma, flatten windows, iterative sine fitting, step order |
| `transit-least-squares/SKILL.md` | TLS search, refinement window, advanced parameters, masking for more planets, SDE/SNR interpretation, alias warning |
| `box-least-squares/SKILL.md` | BLS cross-check, `compute_stats` validation (odd-even, transit count), objectives, grid advice |
| `lomb-scargle-periodogram/SKILL.md` | Stellar-variability diagnosis, period ranges, harmonics and aliases |

Environment facts used: `inputs/environment/Dockerfile` (python 3.12; numpy 1.26.4, scipy
1.13.1, astropy 6.0.1, lightkurve 2.4.2, transitleastsquares 1.32, matplotlib 3.9.0)
and the format of `inputs/environment/data/tess_lc.txt`: four `# columnN:` comment lines
(time (mjd), flux (relative), flag, flux error), whitespace-delimited, 2-min cadence,
about 25 d baseline with a ~2.2 d mid-sector gap, all flags 0. The loader reads the
column roles from those comment lines and falls back to position (time, flux, flag,
flux_err, matching the BLS source's `data[:, 0]`, `[:, 1]`, `[:, 3]`).

## Procedure graph

```
prepare-light-curve (execution) -> search-period (execution) -> vet-candidate (decision)
  -> credible-router (router) --true--> refine-period (execution) -> report-answer (client_task) -> end
                              --false-> investigate-signal (client_task) -> refine-period
```

## Step-kind choices

- **prepare-light-curve: execution.** Everything here is a deterministic rule over the
  data: the flag convention ("check which approach gives cleaner results" becomes a
  scatter comparison), sigma clipping, Lomb-Scargle variability diagnosis, the window
  rule ("longer than transit duration but shorter than stellar rotation period"),
  when to sine-prewhiten, and the second outlier pass.
- **search-period: execution.** TLS broad search, BLS cross-check, top peaks, and every
  number the vetting needs (SDE/SNR tiers, odd-even depths, dip at phase 0.5, SDE at
  P/2 and 2P, empty transits, duration sanity, match to the rotation period). These are
  calculations and thresholds, so they are scripted; the script also emits
  plain-language `vet_flags`.
- **vet-candidate: decision.** Whether the true period is P, 2P or P/2, and whether the
  candidate is credible, are judgments over several diagnostics plus the fold plots,
  with a fixed answer space. A `choice` (`as_found`/`double`/`half`) and a `noul`
  (`signal_credible`) with thresholds (0.75, 0.2) keep them typed and reviewable.
- **credible-router: router** on `signal_credible`, so weak candidates get an
  investigation instead of a confident-looking refinement.
- **investigate-signal: client_task.** Recovering a weak signal is open-ended
  ("try less aggressive outlier removal", "check preprocessing", "extend the range",
  "compare results with different preprocessing"). The agent reruns the scripts with
  overrides (`flatten_window_days`, `prewhiten`, `pass1/2_sigma_upper`,
  `quality_convention`, `period_min/max`, `bls_objective`, `run_tag`) and picks the run.
- **refine-period: execution.** Applying the chosen multiple, the narrow window (+/-5%),
  dense grid, masked re-flatten, trapezoid polish and the final threshold checks are
  all deterministic.
- **report-answer: client_task.** The output format (file, decimals, units) comes from
  free-text task instructions, so the agent writes it.

## Deliberate adaptations (where the pack departs from the literal source text)

- **Upward-only outlier clipping.** Sources say `remove_outliers(sigma=3)` (symmetric).
  Symmetric clipping deletes transit bottoms on a quiet star (a 1-3% dip is 10-30
  sigma). The pack clips upward at 3 (pass 1) and 5 (pass 2) sigma, and removes
  downward points only when they are isolated single-cadence glitches (>10 sigma with
  normal neighbours). This applies the sources' "not too aggressively" and "preserve
  transit shapes".
- **Flatten window in days.** Sources give cadence counts tuned to TESS 2-min
  (300-500). The pack sets 0.5 d (361 cadences at 2-min), shrinks it to 0.25 x the
  rotation period for strong variability, floors it at 0.25 d, and converts to an odd
  cadence count. That way 30-min data is not over-smoothed.
- **Sine prewhitening is gated.** The source loops 50 iterations and warns that it
  removes periodic signals. The pack prewhitens only when variability is strong, not
  transit-shaped (folded low-bin fraction below 0.2), and faster than the safe window.
  It stops when peaks fall under 0.5x the noise, then resets the window to the default.
  Found in testing: a deep hot Jupiter's transit was the dominant Lomb-Scargle peak.
  Without prewhitening, a fast rotator's 0.90 d period beat a real 6.3 d planet in TLS.
- **Masked re-flatten before refinement.** The first flatten under-measured the depth
  by about 30% and produced overshoot shoulders around the transit. Refine re-flattens
  the pre-flatten series with the candidate's transits masked (lightkurve
  `flatten(mask=...)`, `transit_mask` with 2x duration).
- **Trapezoid polish.** After the narrow TLS, a bounded least-squares trapezoid fit
  (P, T0 at mid-data epoch, depth, duration, ingress) gives the final period. It is
  used only when it converges off-bound, lowers chi2, and stays within 3 sigma of the
  TLS period. This implements "refine for precision" beyond the TLS grid step.
- **SDE validation uses the broad search.** SDE is normalised over the searched range,
  so the refine-window SDE (~4) is not comparable with the 6/9 thresholds.
- **Red-noise-aware odd-even.** Odd and even depths come from per-transit depths. Each
  error is the larger of a beta-inflated white error and the per-transit scatter. In
  testing, white-noise errors put a genuine planet under fast rotation at 4 sigma.
- **BLS `depth_snr`.** The BLS source reads `stats['depth_snr']`, which astropy's
  `compute_stats` does not return; the pack computes `depth / depth_err`.
- **TLS `oversampling_factor` default.** The TLS source says the default is 1; the
  library's default is 3. The pack sets 3 (broad) and 10 (refine) explicitly.
- **Rotation-period match flag and duration sanity flag** were added to make "check
  whether the candidate is real, not artifact" and "reasonable duration" scriptable.
- **Fresh-agent fixes.** Two fresh agents found problems that are now fixed:
  - A window override no longer disables prewhitening; prewhitening depends only on
    the variability.
  - `search.py` reads `prep_summary.json` from the variant folder, so the
    rotation-period flag also fires on by-hand runs.
  - The credibility criteria now state the SNR / BLS-support rule once.
  - Refine drops TLS's white-noise odd-even figure, which conflicted with the
    red-noise-aware one.
  - The 2P gap flag says whether both parities have data.
- **No file outputs inside the pack.** Intermediate files go to `$EXO_WORKDIR` or the
  system temp dir.

## Deliberate drops

| Source content | Why dropped |
|---|---|
| Links to Lightkurve/TLS/astropy docs and tutorials; key papers (Hippke & Heller 2019, Kovács et al. 2002, Hartman & Bakos 2016); Lightkurve tutorial section numbers | Bibliographic background, not actionable at run time |
| `pip install ...` dependency blocks | The container ships the packages; recorded in `compatibility` |
| Intro/overview prose ("Preprocessing is essential...", "Lomb-Scargle extends the classical periodogram...", BLS models an upside-down top hat) | Background the agent already knows; the procedure encodes the actions |
| `print(...)` formatting lines in examples; `plt.show()` | Interactive display; plots are saved to PNG files instead |
| "Document your workflow - reproducibility is key" | Satisfied structurally (state, summaries, report); kept as one line in the reference best-practice list |
| "Signal may be too shallow for detection" (as a solution) | Kept as an explanation in the reference; it does not give the agent anything to do |

## Completeness map (source item -> location)

- Pipeline stages and order -> `purpose`; steps prepare -> search -> vet -> refine; `references/preprocessing.md` "Order matters".
- Flag conventions (0 good / 0 bad, verify) -> `prepare.py choose_quality` (scatter test, override), anti-pattern, `references/preprocessing.md`.
- Outlier sigma 3 / 5 / 2 semantics; two passes; outliers before flattening -> `config.json outliers`, `prepare.py`, anti-patterns, reference.
- Flatten window ranges, window rule, Savitzky-Golay -> `config.json detrend`, `prepare.py`, anti-pattern, reference.
- Iterative sine fitting code and warning -> `prepare.py` (gated), reference (code verbatim), anti-pattern.
- Always include flux_err; "flux_err required" issue -> `prepare.py` fallback, `search.py` passes it, anti-pattern, reference.
- Visualize each step -> `prepare.png`, `search.png`, `refine.png`; decision input description; investigate template.
- Algorithm choice TLS / BLS / LS (when to use, pros and cons) -> `search.py` (TLS primary, BLS cross-check), `prepare.py` (LS for variability), anti-pattern (no LS for transit periods), `references/period-search-methods.md` table.
- Period ranges (hot Jupiter, warm, habitable zone; LS science-case ranges; baseline) -> start inputs `period_min/max` (0 = auto, baseline/2), reference.
- TLS usage and result attributes, period_uncertainty, folded arrays, model light curve -> `search.py`/`refine.py`, reference.
- Refinement (narrow +/-2-10%, +/-5% typical, finer grid) -> `refine.py` + `config.json refine`, anti-pattern, reference.
- Advanced TLS parameters (oversampling_factor, duration_grid_step, T0_fit_margin) -> `config.json`, reference.
- SDE > 9 / > 6 / < 6, SNR > 7 -> `config.json validation`, `search.py` tiers and vet flags, `refine.py` validation, decision criteria, reference.
- TLS warning "X of Y transits without data" / empty transits / aliasing -> `search.py` (captures stdout warnings, `empty_transit_count` flag), decision `period_choice`, reference.
- Period 2x / 0.5x causes and fixes (check both, phase folds, odd-even) -> `search.py` alias_checks + folds at P, 2P, P/2; decision `period_choice`; reference.
- Odd-even mismatch (> 3 x depth_err) -> `search.py`/`refine.py odd_even`, BLS stats, decision, reference.
- Multiple transits = more confidence -> `transits_with_data`, `min_transits_with_data`, decision.
- Reasonable duration for the orbit -> `search.py` duration flag, decision instructions.
- BLS autopower vs power, autoperiod, objectives (likelihood / snr), durations, compute_stats, top-5 peaks -> `search.py run_bls` (objective override), `top_peaks`, reference.
- Multi-planet: mask, search again, repeat -> `refine.py search_additional_planets` (+ harmonic guard), reference, report template step 3.
- Low SDE fixes (less aggressive preprocessing, gaps, wider range, wider durations) -> investigate template, reference.
- Results vary with preprocessing -> investigate template (compare variants), reference.
- Expected transit depths -> `references/validation-troubleshooting.md`.
- LS: `view='period'`, harmonics and aliases, model fitting -> reference; harmonic relations in `top_peaks`.
- Phase folding -> plots, reference.
