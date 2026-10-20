# transit-period-finder: sources, design, and drop log

## Provenance

Compiled on 2026-10-20 into one AIP 0.6a1 skill from five curated Agent Skills that
together describe one workflow (find a transiting planet's period under stellar
activity). The originals are copied verbatim:

| Source | Copied to |
|---|---|
| `inputs/skills/box-least-squares/SKILL.md` | `source/box-least-squares/SKILL.md` |
| `inputs/skills/exoplanet-workflows/SKILL.md` | `source/exoplanet-workflows/SKILL.md` |
| `inputs/skills/light-curve-preprocessing/SKILL.md` | `source/light-curve-preprocessing/SKILL.md` |
| `inputs/skills/lomb-scargle-periodogram/SKILL.md` | `source/lomb-scargle-periodogram/SKILL.md` |
| `inputs/skills/transit-least-squares/SKILL.md` | `source/transit-least-squares/SKILL.md` |
| task statement the downstream agent receives | `source/task-instruction.md` |

The source skills hold only SKILL.md files (no scripts/, references/ or assets/).

Target runtime: the task container (`python:3.12-slim` with numpy 1.26.4, scipy 1.13.1,
astropy 6.0.1, lightkurve 2.4.2, transitleastsquares 1.32, numba 0.60, batman 2.5.2).
The scripts import only numpy, scipy, astropy, lightkurve and transitleastsquares. They were
tested under that pinned stack (Python 3.12 venv) and under the aip CLI's Python 3.14.

## Intent

The task gives one TESS light curve (time, normalized flux, quality flag 0 = good, flux
error) with strong rotational modulation hiding a transiting planet, and asks for the
period, written as a single number rounded to 5 decimals. The skill has to work on any
instance of that task, so nothing about this file's answer is encoded. Every number comes
from the data at run time.

## Graph and component-kind choices

```
prepare (execution) -> search (execution) -> vet (decision) -> route-credible (router)
   true  -> finalize (execution) -> end
   false -> rescue (client_task) -> write-rescue (execution) -> end
```

| Step | Kind | Why |
|---|---|---|
| prepare | execution | Loading, the flag convention, non-finite removal, sigma clipping, Lomb-Scargle: deterministic rules and numerics. |
| search | execution | Detrending, BLS/TLS searches, refinement, model fit and vetting statistics are all numeric. The window rule (fractions of the rotation period, floor 0.12 d, cap 1.5 d) and the selection rule (max BLS SDE) are deterministic. |
| vet | decision | Whether a signal is a credible transit and which alias (P, P/2, 2P) is the true period is a judgment over many statistics. The answer space is fixed (noul + 3-label choice), and the source thresholds (SDE 6/9, SNR 7, odd/even 3 sigma, >=2 transits) sit in the criteria. |
| route-credible | router | Credible signals take the scripted path; non-credible ones need open-ended work. |
| finalize | execution | Picking the reported value or re-fitting the chosen alias, then formatting to 5 decimals. Deterministic. |
| rescue | client_task | A failed automated search needs open-ended investigation (other windows, pre-whitening, wider ranges). The agent must produce a number, so it is a client task, guided by `assets/rescue.md` and `references/transit-search-methods.md`. |
| write-rescue | execution | The same deterministic formatting for the rescue period. |

The keys on the two branches differ (one producer per key), so `end` returns the keys
common to both paths (`output_path`, `candidate`). The answer itself is the file at
`output_path`.

### Design decisions beyond the sources (from functional testing on the real file)

- **Flatten window tied to the rotation period.** On the task file (rotation ~1.4 d), windows
  of 0.14-0.6 d all recover the same transit period. A ~1 d window (701 cadences, near the
  rotation period) returned a spurious ~7.15 d period with TLS. The source rule "longer than
  the transit, shorter than the rotation period" is therefore enforced in code: windows are
  0.1-0.4 x P_rot (fixed 0.25-1.0 d when no clear rotation), and the best is picked by BLS SDE.
  `windows_agreeing_with_period` tells the vet step whether the period is robust to that choice.
- **Transit-masked re-flatten.** Short windows give the highest SDE but shrink the depth
  (0.7 ppt at 0.14 d vs 2.1 ppt at 0.56 d). After detection the curve is re-flattened with
  the transits masked (lightkurve `flatten(mask=...)`), so the refinement sees the true depth.
- **Trapezoid ephemeris fit for the final digits.** TLS and BLS grid periods are only good to a
  fraction of the peak width (TLS `period_uncertainty` 0.015 d here). A least-squares
  trapezoid fit over all transits, seeded by a (P, t0) grid, gives ~0.0002 d. On the task file:
  TLS 5.3579, BLS fine grid 5.35846, fit 5.35845 +/- 0.0002. A local-quadratic-baseline variant
  agreed within 0.2 sigma. On an injected-planet test (true P 3.71234), the fit returned 3.71302
  +/- 0.0005 (1.3 sigma). It falls back to TLS if the fit fails or leaves the search window.
- **Asymmetric outlier clipping.** The sources' `remove_outliers(sigma=3)` is symmetric on the
  global flux. On a rotating star it clips rotation extremes, and on a deep hot-Jupiter
  transit it can delete the transit. The scripts clip the upper side at 3 sigma (pre-flatten,
  relative to a running median shorter than P_rot/6) and at 5 sigma after flattening,
  following the source's "3 for initial, 5 after flattening". Negative points are clipped
  only as isolated single cadences beyond 5 sigma.
- **flag_convention start input.** The source says conventions vary (flag 0 can be good or bad),
  so the caller states it from the task text. The script stops with a clear message if the
  chosen convention leaves no data.
- **TLS SDE inside the +/-5% refinement window is meaningless** (4.8 on the real file), so only
  the broad-search SDE is reported.

## Completeness check (source item -> where it lives)

Legend: P = prepare.py, S = search.py, F = finalize.py, V = vet decision, R =
references/transit-search-methods.md, A = anti_patterns, T = assets/rescue.md, Q = requires.

### box-least-squares
- BLS concept, the four searched parameters, Kovács 2002 basis: R (BLS section); S uses BLS.
- Installation (astropy): Q.
- Basic usage, autopower vs power, custom grids, multiple durations: R; S (`autoperiod` + `power` with a duration list).
- "Period grid quality matters": R; S uses `frequency_factor=1.0` and a 20001-point fine grid.
- Objectives likelihood / snr, SNR robust to correlated noise: R; S uses snr for the scan and likelihood for the fine grid.
- Complete example: S/R. The plotting part is dropped (below).
- compute_stats, depth/odd/even/transit_count, odd-even > 3 x depth_err warning: S `bls_stats`; V criteria; R table.
- Validation criteria (SNR > 7, low odd-even, multiple transits, reasonable duration): V signal_credible.
- autoperiod grid, finer grids around candidates, grid matters more than for LS: S; R.
- Comparing top 5 peaks: R (BLS section); S's window scan and alias table give the automated comparison.
- Phase-folded light curve: replaced by numeric phase statistics (depth_at_phase_0p5 at P and 2P) in S/V; R says to fold in manual work.
- BLS vs TLS pros/cons, "try both": R; S runs TLS (primary) and BLS (scan + cross-check).
- Integration-with-preprocessing pipeline 1-5 and key considerations: the procedure order; A.
- Common issues (no clear peak, 2x/0.5x, high odd-even), causes and fixes: R common problems; V period_choice; T.
- When to use BLS/TLS/LS: R; do_not_use_when (rotation-only goals).

### exoplanet-workflows
- Overview and key stages (load, QC, preprocess, search, validate, refine): the step sequence.
- Critical decisions (outliers yes but gentle; detrend because rotation masks transits; balance): P/S clipping rules; A.
- Algorithm choice (TLS best, LS exploration, BLS alternative, TLS generally better than BLS): R; S makes TLS primary.
- Period range by planet type (hot Jupiter 0.5-10 d etc.) and "wider = slower": R; S searches 0.3 d to baseline/2.
- When to refine (narrow search around the candidate): S (+/-5% TLS, fine BLS, fit).
- Method sections (TLS/LS/BLS use-when, advantages, disadvantages): R.
- Signal validation (SDE > 9 / > 6, SNR > 7, warning signs, how to validate): V; R table.
- Multi-planet strategy and transit_mask: R; T.
- Common issues (low SDE, 2x/0.5x, flux_err required, results vary with preprocessing): R; A; S window agreement metric.
- Expected depths (hot Jupiter 1-3 %, super-Earth 0.1-0.3 %, Earth 0.01-0.1 %): R; V depth plausibility.
- Period range guidelines incl. habitable zone: R.
- Best practices: flux_err always (P/S, A); check flag convention (P flag_convention input); sigma 3 then 5 (P/S); refine (S); validate (V); data gaps -> aliasing (V, A); document (prep_summary, candidate, rescue_notes). "Visualize each step" is dropped (below).

### light-curve-preprocessing
- Outlier removal with lightkurve, sigma 2/3/5 meanings: R; P/S implement the upper-side variant (see design decisions).
- Manual median/std clipping: P (running-median residual, MAD sigma).
- Flatten with window_length, typical window ranges, SG preserves transits: S `flatten`; R.
- Iterative sine fitting, plus its warning that it removes periodic signals: R (code + warning); T step 3.
- Quality flags: the TESS flag==0 good convention, the alternative flag==0 bad, "verify your format": P flag_convention; R.
- Pipeline order (flags -> outliers -> trend -> optional second pass): P then S.
- Principles (flux_err, preserve transit shape, don't over-process, verify): P/S; A.
- Parameter selection (sigma ranges, window longer than transit / shorter than rotation, two passes): S window rule (MIN_WINDOW_DAYS, fractions of P_rot); P/S two passes.
- Preprocessing for exoplanet detection (sigma 3 or 5, appropriate window, don't over-smooth): P/S.
- Best practices 1-5: P/S order; S window rule.

### lomb-scargle-periodogram
- LS for unevenly sampled data; lightkurve `to_periodogram`, `period_at_max_power`: P uses astropy `LombScargle` (the engine behind lightkurve's LS periodogram) for the rotation period; R gives the lightkurve form.
- Plot with view='period': R (one comment). Plotting otherwise dropped.
- Period range selection (rotation 0.1-100 d, transits 0.5-50 d, EBs, pulsations): P (0.1 d to min(100 d, baseline/2)); R.
- Interpreting power, harmonics, aliases: S `period_matches_rotation_harmonic`; V; R.
- Model fitting (`pg.model`): R (sine-fitting recipe).
- When to use LS vs TLS/BLS, "TLS after LS": the procedure (LS for rotation, TLS for transits).

### transit-least-squares
- Install; flux_err CRITICAL: Q; S always passes flux_err; A.
- Usage via lightkurve -> remove_outliers -> flatten -> TLS: P/S.
- Result attributes (period, period_uncertainty, T0, depth, snr, SDE): S candidate; R.
- Explicit period range: S (0.3 d to baseline/2).
- Refinement strategy (broad then +/-2-10 %): S (+/-5 %, oversampling 10); R.
- Advanced options (oversampling_factor, duration_grid_step, T0_fit_margin): R; S uses oversampling_factor.
- Phase-folding attributes, model light curve attributes: R.
- Transit masking for further searches: S (masked re-flatten); R multi-planet.
- SDE and SNR interpretation thresholds: V; R.
- "X of Y transits without data" warning -> check 2P: V period_choice (empty_transit_count alone is not evidence); A; R.
- Workflow considerations and typical parameter ranges: the procedure; S constants.
- Multiple-planet search strategy: R.
- Common issues (flux_err, 2x/0.5x, low SDE -> less aggressive flattening, gaps during transits): R; T.

### task-instruction.md
- Input columns (time MJD, flux, flag 0 = good, flux error): P loader default order and header parsing; flag_convention.
- Filter, remove activity, find the period: prepare / search.
- Output: one number in days, 5 decimals, at /root/period.txt: F / write_period.py (`f"{p:.5f}"`); A.

## Deliberate drops

| Dropped | Rationale |
|---|---|
| All matplotlib plotting snippets and "visualize each step / plot before and after" advice | The run is headless and autonomous. Nobody looks at the plots. Their purpose (check the transit survives, check folds, compare preprocessing) is covered by numeric checks: depth per window in `window_scan`, depth_at_phase_0p5, odd/even, window agreement. The rescue reference still says to phase-fold when working by hand. |
| `pip install` commands | The container already has the packages; `requires` declares them and the client checks before the first script. |
| Documentation links, tutorial section numbers, paper citations (Kovács 2002, Hippke & Heller 2019, Hartman & Bakos 2016) | Background. Not actionable at run time. |
| Introductory prose ("BLS is a statistical tool...", "LS extends the classical periodogram...") | The agent already knows this. |
| Duplicate statements across the five skills (preprocessing order, 2x/0.5x aliasing, flux_err warnings repeated 3-4 times) | Kept once each, in the place they act (script, decision criterion, anti-pattern, or reference). |
| `print(...)` formatting in examples | Superseded by the structured JSON outputs. |
