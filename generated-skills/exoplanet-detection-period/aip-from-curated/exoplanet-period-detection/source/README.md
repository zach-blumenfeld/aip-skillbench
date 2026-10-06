# Provenance

This AIP skill was compiled on 2026-10-06 from five curated Agent Skills
that together describe one workflow: detecting an exoplanet orbital
period in a photometric light curve.

| Source skill | Verbatim copy at |
| --- | --- |
| `box-least-squares` | `source/box-least-squares/SKILL.md` |
| `exoplanet-workflows` | `source/exoplanet-workflows/SKILL.md` |
| `light-curve-preprocessing` | `source/light-curve-preprocessing/SKILL.md` |
| `lomb-scargle-periodogram` | `source/lomb-scargle-periodogram/SKILL.md` |
| `transit-least-squares` | `source/transit-least-squares/SKILL.md` |

The reference execution environment is defined by
`../../../inputs/environment/Dockerfile` (python:3.12-slim +
numpy 1.26.4, scipy 1.13.1, astropy 6.0.1, lightkurve 2.4.2,
transitleastsquares 1.32, batman-package 2.5.2). The scripts shipped in
this skill work against that stack and against newer compatible pins
(astropy 8.x, transitleastsquares 2.x) used in local testing.

# Procedure graph

Starts at `load-lightcurve`. One method router (TLS/BLS/LS) selects the
search backend; one strength router decides whether to refine. End
state carries `method`, `detection`, `strength`, `aliasing_suspected`,
and (when refinement ran) `detection_refined` as a pass-through key.

```
load-lightcurve
      │
      ▼
 pick-method (decision: method=tls|bls|ls)
      │
      ▼
 route-method (router)
   │   │   │
   ▼   ▼   ▼
 search-tls / search-bls / search-ls
      │
      ▼
 validate-detection (decision: strength + aliasing_suspected)
      │
      ▼
 route-strength (router)
   │                 │
   ▼                 ▼
 refine-period      end  ← weak
      │
      ▼
     end  ← strong / moderate
```

# Step-kind choices

- `load-lightcurve` → **execution**. Pure data munging: file parse,
  dtype coerce, median normalisation, quality mask. Deterministic logic
  over structured inputs → script.
- `pick-method` → **decision**. The algorithm choice depends on the
  shape of the task (planet vs variability) and the data properties.
  Judgement over a closed set of three labels → choice question. A
  router cannot do this: the question is "which of these three best
  fits?", not a mechanical dispatch.
- `route-method` → **router**. Mechanical fan-out on the decision's
  answer. No judgement, no model.
- `search-tls`, `search-bls`, `search-ls` → **execution**. Library
  calls into `transitleastsquares` and `astropy.timeseries`. All
  deterministic once the method is picked.
- `validate-detection` → **decision**. Judging a candidate against
  SDE/SNR/FAP/odd-even thresholds has structured criteria but requires
  interpretation across method-specific metrics; a choice question
  captures the three strength classes, a noul captures the aliasing
  flag. The method-specific thresholds are listed inside `instructions`
  so one call answers both.
- `route-strength` → **router**. Mechanical dispatch on the strength
  label.
- `refine-period` → **execution**. Narrow re-run of the same algorithm
  over a window around the candidate — deterministic.
- `end` → terminal. Final state carries the method, raw detection,
  strength, and aliasing flag. `detection_refined` is not declared in
  the end inputs because it is only present on the refine path; extra
  keys pass through.

# Line-by-line completeness check

Each curated source skill was walked once. Items placed in SKILL.md
(body, scripts, references, decision criteria) are marked ✅ with the
location. Items deliberately dropped are marked ✗ with rationale.

## source/exoplanet-workflows/SKILL.md

- "Data loading and quality control" ✅ `load_lightcurve.py` + input
  `quality_good_is_zero`.
- "Preprocessing to remove instrumental and stellar noise" ✅
  `_preprocess.py` (sigma clip + Savitzky-Golay); documented in
  `references/preprocessing-recipes.md`.
- "Period search using appropriate algorithms" ✅ `pick-method` +
  three search scripts.
- "Signal validation and characterization" ✅ `validate-detection`
  decision with SDE/SNR/FAP thresholds.
- "Parameter estimation" ✅ `refine-period` execution.
- "Preprocess: Remove outliers (not too aggressively), remove trends,
  balance noise vs signal" ✅ sigma defaults 5/3 + 101-cadence window;
  rationale in `references/preprocessing-recipes.md`.
- "Which period search algorithm: TLS / Lomb-Scargle / BLS" ✅
  `pick-method` criteria + `references/method-selection.md`.
- "Period range to search: Hot Jupiters 0.5-10 d, warm 10-100 d,
  habitable zone 200-400 d (G) or 10-50 d (M)" ✅
  `references/method-selection.md` and in the start-input descriptions
  (`period_min`, `period_max`).
- "When to refine: after promising candidate, ±2-10 % around candidate"
  ✅ `refine-period` uses ±5 % (or 5× period_uncertainty).
- "Choosing the right method (TLS/LS/BLS pros & cons)" ✅
  `references/method-selection.md` and `pick-method` criteria.
- "Signal validation: SDE > 9 very strong, SDE > 6 strong, SNR > 7
  reliable, warnings (low SDE, period×2, odd-even mismatch)" ✅
  `validate-detection` and `references/method-selection.md`.
- "How to validate: metrics, visual inspection, odd-even, multiple
  transits" ✅ odd-even is computed by `search_tls.py`/`search_bls.py`
  and consumed by `validate-detection`. Visual inspection is ✗
  **deliberate drop**: this skill produces numeric detections; plot
  generation would require matplotlib display or file output outside
  the AIP state. Odd-even and transit-count checks are the automatable
  equivalents.
- "Multi-planet systems: mask the first planet, re-search" ✗
  **deliberate drop**: scope of this skill is single-planet period
  detection. Multi-planet search would need an iteration construct
  AIP does not yet express; mentioned in
  `references/troubleshooting.md` for the agent to handle manually if
  needed.
- "Common issues: No significant detection, period 2×/0.5× expected,
  flux_err required, results vary with preprocessing" ✅
  `references/troubleshooting.md`.
- "Expected transit depths (hot Jupiter 1-3 %, super-Earth 0.1-0.3 %,
  Earth-sized 0.01-0.1 %)" ✗ **deliberate drop**: context only, not
  actionable in the graph. The validation thresholds already encode
  how depth maps to detectability through SDE/SNR.
- "Period range guidelines by target" ✅ above.
- "Best practices (flux_err, visualise, quality flags, sigma,
  refinement, validation, data gaps, documentation)" ✅ covered by
  anti-patterns, `preprocessing-recipes.md`, and `troubleshooting.md`.
- References section (lightkurve tutorials, TLS GitHub, Hippke &
  Heller 2019, Kovács et al. 2002) ✗ **deliberate drop**: provenance
  pointers for a human reader; the agent does not need to open them to
  run the procedure. Preserved verbatim under `source/`.

## source/light-curve-preprocessing/SKILL.md

- "Remove outliers (sigma=3 standard, 5 conservative, 2 aggressive)"
  ✅ `_preprocess.py` default sigma1=5, sigma2=3; override noted in
  `preprocessing-recipes.md`.
- "Flatten with window_length (100-200 short, 300-500 medium,
  500-1000 long)" ✅ default 101 for 30-min cadence; `preprocessing-
  recipes.md` describes when to raise to 501+ for short-cadence data.
- "Iterative sine fitting for stellar rotation" ✗ **deliberate drop
  from the graph**, retained as a recipe in
  `preprocessing-recipes.md`. Sine fitting itself removes periodic
  signal and so is unsafe to call unconditionally in a transit-search
  pipeline; the agent should invoke it only when rotation is known to
  dominate.
- "Quality flag conventions (TESS flag==0 good vs flipped)" ✅
  `quality_good_is_zero` input to `load-lightcurve`.
- "Order matters: quality → outliers → trend → second-pass outliers"
  ✅ `_preprocess.py` implements this exact order; documented in
  `preprocessing-recipes.md`.
- "Always include flux_err" ✅ anti-pattern + fabricated fallback in
  `load_lightcurve.py`.
- "Preserve transit shapes" ✅ Savitzky-Golay + second clip is
  one-sided (upward only) to preserve dips.
- "Don't over-process; verify visually" ✅ anti-pattern.
- "Parameter selection (sigma, window, two passes)" ✅
  `preprocessing-recipes.md`.
- Code snippets using lightkurve `remove_outliers`, `flatten`,
  `to_periodogram` ✗ **deliberate drop**: we implement the same
  pipeline in numpy/scipy + astropy so the skill does not require
  lightkurve at runtime. Equivalent behaviour is in `_preprocess.py`.
- "Visualising results (lc.plot())" ✗ **deliberate drop**: output
  medium is JSON state, not plots. See exoplanet-workflows drop above.

## source/lomb-scargle-periodogram/SKILL.md

- "Create periodogram with maximum_period / minimum_period" ✅
  `search_ls.py` uses `autopower(minimum_frequency, maximum_frequency)`
  derived from `period_max` / `period_min`.
- "`pg.period_at_max_power`, `pg.max_power`" ✅ `search_ls.py` picks
  argmax(power) and reports period, power, and FAP.
- "view='period' not 'frequency'" ✗ **deliberate drop**: plotting
  guidance; we return numeric values keyed by `period` directly.
- "Period range by science case (rotation, transits, EB, pulsations)"
  ✅ `references/method-selection.md`.
- "Power significance: high power real, multiple peaks → harmonics,
  aliasing" ✅ `aliasing_suspected` question in `validate-detection`
  and `references/method-selection.md`.
- "Common patterns: single strong peak, harmonics P/2 and 2P, aliases"
  ✅ `references/method-selection.md` and `troubleshooting.md`.
- "Model fitting (pg.model, frequency_at_max_power)" ✗ **deliberate
  drop**: downstream consumer of the detected period; not required to
  deliver the period itself.
- "When to use LS vs TLS vs BLS" ✅ `pick-method` criteria and
  `references/method-selection.md`.

## source/box-least-squares/SKILL.md

- "Prepare data with astropy units; BoxLeastSquares(t, y, dy=dy)" ✅
  `search_bls.py`.
- "autopower with duration (or multiple durations)" ✅ `search_bls.py`
  uses `np.linspace(0.05, 0.3, 8) * u.day`.
- "power with custom period grid" ✅ `refine_period.py` uses a dense
  custom grid around the candidate.
- "Objective likelihood vs snr" ✅ `search_bls.py` uses `'likelihood'`
  (the astropy default and the first option in the source skill);
  `objective='snr'` is noted in `references/method-selection.md` as an
  override for correlated-noise cases.
- "compute_stats: depth, depth_err, depth_snr, odd-even, transit_count"
  ✅ `search_bls.py` returns these.
- "Peak statistics for validation" ✅ `validate-detection`.
- "Period grid sensitivity (autoperiod)" ✅ handled by `autopower` in
  the first pass and dense `power` grid in refinement; discussed in
  `method-selection.md`.
- "Comparing BLS results — top 5 peaks" ✗ **deliberate drop**: single-
  candidate pipeline. Multi-candidate exploration is outside this
  skill's scope.
- "Phase-folded light curve" ✗ **deliberate drop**: visualisation; see
  earlier.
- "BLS vs TLS: pros/cons, 'try both'" ✅ `pick-method` and
  `references/method-selection.md`.
- "Integration with preprocessing" ✅ `_preprocess.py` is called by
  `search_bls.py`.
- "Common issues (no clear peak, period 2×/0.5×, high odd-even
  mismatch)" ✅ `references/troubleshooting.md`.

## source/transit-least-squares/SKILL.md

- "Install with pip install transitleastsquares" ✅ compatibility note
  in frontmatter.
- "flux_err REQUIRED" ✅ anti-pattern + fabrication fallback.
- "Basic usage: transitleastsquares(time, flux, flux_err).power()" ✅
  `search_tls.py`.
- "Explicit period_min / period_max" ✅ `search_tls.py` passes both
  through from the state.
- "Period refinement: narrow range around candidate" ✅ `refine_period.py`
  (TLS branch) uses `period * [1-h, 1+h]` where h is driven by
  `period_uncertainty` or defaults to 5 %. The source skill suggests
  ±2-10 %; this skill picks 5 % as the default. See
  `references/method-selection.md`.
- "Advanced: oversampling_factor, duration_grid_step, T0_fit_margin"
  ✅ `oversampling_factor=5` is used in the refinement run; the other
  two advanced knobs are left at library default (noted as deliberate
  drop below).
- Duration-grid and T0 fit margin tuning ✗ **deliberate drop**:
  library defaults are tuned for typical light curves; adjusting them
  belongs in a follow-up skill for high-precision characterisation.
- "Phase-folding" ✗ **deliberate drop**: visualisation.
- "Transit masking for multi-planet systems" ✗ **deliberate drop**:
  single-planet scope; noted in `troubleshooting.md`.
- "Interpreting results: SDE > 6 strong, > 9 very strong, SNR > 7
  reliable" ✅ `validate-detection` criteria text.
- "TLS warnings about transits without data (period aliasing)" ✅
  `aliasing_suspected` noul in `validate-detection`.
- "Model lightcurve plotting" ✗ **deliberate drop**: visualisation.
- "Common issues: flux_err required, 2×/0.5× period, low SDE" ✅
  `references/troubleshooting.md`.
