# Source and provenance: tess-transit-period

## Provenance

Compiled on 2026-10-20 from five curated Agent Skills, copied verbatim here:

| Source | Covers |
|---|---|
| `box-least-squares/SKILL.md` | astropy BLS: autopower/power/autoperiod, objectives, compute_stats validation, BLS vs TLS |
| `exoplanet-workflows/SKILL.md` | pipeline stages, method choice, validation thresholds, multi-planet strategy, depth/period context, best practices |
| `light-curve-preprocessing/SKILL.md` | outlier removal, flatten windows, iterative sine fitting, quality-flag conventions, pipeline order |
| `lomb-scargle-periodogram/SKILL.md` | lightkurve Lomb-Scargle, period ranges, harmonics/aliases, model fitting |
| `transit-least-squares/SKILL.md` | TLS usage, flux_err requirement, refinement strategy, advanced params, transit_mask, SDE/SNR thresholds |

Target task: `instruction.md`, a TESS 2-min light curve (`time flag flux flux_err`; flag 0 = good) of an active star whose rotational modulation hides a planet. Write the period, rounded to 5 decimals, to a text file. Container: python:3.12-slim with numpy 1.26.4, scipy 1.13.1, astropy 6.0.1, lightkurve 2.4.2, transitleastsquares 1.32, batman-package 2.5.2.

Intent: the five sources are general tutorials. This skill fixes one concrete, validated pipeline. It turns their "it depends" advice (which window, which sigma, which period, is it an alias) into deterministic rules in one script, plus two typed decisions.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Environment check | execution (one-liner) | deterministic import test |
| `input_format` (column order, flag convention) | decision (choice ×2) | needs reading the task text and file header against each other; the answer space is fixed; feeds `--cols` / `--flag-good` |
| Load, flag filter, clipping, Lomb-Scargle rotation, window rule, flatten/sine detrend, error inflation, TLS broad + refine, harmonic skipping, BLS alias table, batman fit, flag rules, output writing | execution (`scripts/find_period.py`) | all numeric calculations, thresholds and if/then rules over structured inputs. One script, because every stage feeds the next and splitting it would only add file I/O |
| `candidate_verdict` (verdict + is_planet_like) | decision (choice + noul) | mapping a set of flags to an action is mostly mechanical, but close calls (moderate SDE, borderline odd/even) need judgment. The answers are a fixed set, and each maps to an exact rerun option |
| Act on verdict | execution (rerun with options) | each verdict maps to a specific flag (`--force-factor`, `--detrend sine`, `--window-days`, `--mask`, `--flag-good`, `--cols`) |
| Output verification | execution (one-liner regex) | deterministic format check |

No client task is needed. The deliverable is a number the script writes. The agent's only free-form output is the final message.

## Design decisions made during functional testing (beyond the sources)

- **Asymmetric clipping** (upper 3σ, lower 10σ before and 20σ after detrending), instead of the sources' symmetric `remove_outliers(sigma=3/5)`. On flattened data, symmetric 3σ deletes in-transit points of a ~2000 ppm transit at ~1100 ppm scatter. It honours the sources' "don't remove the transit" principle.
- **Window rule** `min(0.5 d, max(P_rot/3, 0.25 d))`, automatically retried at 0.15 d when residual scatter is > 1.5× the errors. On the real file (P_rot = 1.40 d), windows of 0.25–0.5 d recover 5.357 d, while 0.75 d and 1.0 d lock onto rotation residuals at ~12.9 d. On a synthetic 0.35-d rotator, 0.25 d failed and 0.15 d recovered the injected 2.2 d. The sources only say "longer than transit, shorter than rotation; 300–500 cadences typical for TESS".
- **Rotation-harmonic peak skipping** (within 1% of P_rot/k or k·P_rot/2), needed for the fast-rotator case.
- **flux_err inflation** to the residual scatter. Without it, BLS odd/even σ came out 3.8σ on the real planet (a false EB flag); with it, 0.6σ.
- **No masked re-flatten.** Tried, and it raised the TLS odd/even mismatch to 2.4–4σ on the real file by interpolating the spot trend under the transits. The period didn't change. Removed.
- **SDE taken from the broad search.** The refined-window SDE was 4.8 for a clear detection, because SDE is normalised over the searched range.
- **TLS refined period is the reported value.** This follows the sources' refinement strategy. The batman fit (5.35857 ± 0.00039 vs TLS 5.35792 ± 0.0098 on the real file) is a reported cross-check with a disagreement flag, not the answer.
- **astropy 6 gotcha:** the source's `stats['transit_count']` raises KeyError. The script uses `per_transit_count`, and the body and reference document it.

## Deliberate-drop log

| Source item | Why dropped |
|---|---|
| Installation / `pip install` blocks (all five) | packages are preinstalled in the container; the body forbids installing |
| Background prose ("BLS is a statistical tool…", "Lomb-Scargle extends the classical periodogram…", "Preprocessing is essential…") | explanatory; the agent knows it |
| Plotting code (`plt.plot`, `lc.plot()`, `pg.plot(view='period')`, folded/model plots) and "visualize each step" | no human viewer in the autonomous task. Visual inspection is replaced by the scripted odd/even, P/2, 2P and harmonic checks. `view='period'` and the plot advice are kept in references/methods.md for interactive debugging |
| Links to docs, tutorials and papers (Kovács 2002, Hartman & Bakos 2016, Hippke & Heller 2019, Lightkurve tutorial section numbers) | citations, not actionable offline |
| "Document your workflow – reproducibility" | satisfied by the `--json` report |
| Lomb-Scargle model fitting / plotting data vs model | used only inside the sine-detrend branch, which the script implements |
| BLS `objective='likelihood'` default vs `'snr'` | the script uses `objective='snr'` (the source notes it is more robust to correlated noise, which applies to active stars); both are documented in the reference |
| Radial velocity, pulsation and eclipsing-binary period ranges | outside a transit-period task. Kept in the reference for completeness |

Everything else (thresholds SDE 6/9 and SNR 7, odd/even 3σ, sigma choices, window guidance, flag conventions, refinement ±2–10% / ±5%, oversampling, duration grid, T0 margin, transit_mask multi-planet loop, alias causes and remedies, the "X of Y transits without data" warning, expected depths, period ranges, the method-choice rationale, low-SDE remedies) is carried in `SKILL.md`, `scripts/find_period.py` or `references/methods.md`.

## Completeness walk (source → where carried)

- box-least-squares: basic usage, autopower/power/autoperiod, objectives → reference "BLS". compute_stats validation (depth SNR > 7, odd/even > 3σ, multiple transits, reasonable duration) → script `bls_fine` + flag rules + `is_planet_like`. Top-5 comparison → script `tls_top_peaks` + reference. Phase fold → reference. BLS vs TLS and when to use each → SKILL Purpose / step 3 (TLS primary, BLS cross-check) + reference. Preprocessing pipeline order → script stages. Common issues (no peak, 2×/0.5×, odd/even) → flags + verdict criteria + step 5 retries + reference.
- exoplanet-workflows: stages and critical decisions → Procedure. Method choice → TLS primary, Lomb-Scargle for rotation only (Gotchas), BLS check. Period range by planet type → step 5 retry 3 + reference. Validation thresholds and warning signs → flag table. Multi-planet → `mask_and_research` + `--mask`. Common issues (low SDE, 2×, flux_err required, results vary with preprocessing) → flags, step 5, Gotchas. Expected depths → `is_planet_like` + reference. Best practices 1–8 → errors always passed and inflated; flag check; sigma 3 then 5 → asymmetric clipping (see design decisions); refine; validate; gaps flag; JSON report.
- light-curve-preprocessing: outlier removal (lightkurve and manual) → script `clip` + reference. flatten windows → window rule + Gotchas + reference. Iterative sine fitting + warning → `--detrend sine` + step 5 caveat. Flag conventions → `input_format` + script check. Order and principles → script order. Parameter selection → script defaults + reference.
- lomb-scargle-periodogram: usage → script `rotation()` + reference. Period ranges → reference. Harmonics/aliases → harmonic skipping and flag. "Use TLS after Lomb-Scargle" → pipeline order.
- transit-least-squares: flux_err critical → script + Gotchas. Period-range search → `--period-min/max`. Refinement ±2–10% → script ±5%, `oversampling_factor=10`. Advanced params → script (`duration_grid_step=1.1`) + reference. Folded and model outputs → reference. transit_mask → `--mask`. SDE/SNR thresholds → flags. "transits without data" warning → gaps flag + Gotchas. Workflow and parameter ranges → Procedure. Common issues → flags/step 5.

## Functional test record (2026-10-20, in the task's Docker image built from the Dockerfile)

Walked the skill's steps 1–6 with the body's launch commands, the skill mounted read-only, and the real `/root/data/tess_lc.txt`. Decisions: `column_order=default`, `flag_convention=zero_good`, `verdict=accept` (only the informational gaps flag), `is_planet_like=true`. Output `5.35792` (TLS refined; BLS 5.35914; batman 5.35857 ± 0.00039; P_rot 1.397 d; 4 transits with data, odd/even 0.6σ; P/2 = 2.679 has empty odd epochs). Runtime is about 25 s on 2 CPUs.

Branch coverage (synthetic instances made by injecting batman transits into multi-sinusoid spot models with flares and flagged bad points, plus variants of the real file):

| Case | Branch exercised | Result |
|---|---|---|
| 30-min cadence, comma-delimited, P_rot 3.2 / P 3.8 | default path, window in cadences | 3.80131 ✓ |
| P_rot 0.35 d, P 2.2 | auto window retry 0.15 d + harmonic-peak skipping | 2.20005 ✓ (before these rules: 0.70 = 2·P_rot) |
| flags inverted, P 6.3 | flag-convention warning → `fix_flags` → `--flag-good nonzero` | 6.30017 ✓ |
| no planet | weak flags → `retry_detrend` / report-weak | flagged weak ✓ |
| EB, unequal eclipses, P 4.4 | odd/even 16σ at P, 4.8σ at 2P → `use_double` → `--force-factor 2`; `is_planet_like=false` | 4.40041 ✓ |
| P 11.7, two transits | `--period-min/--period-max` narrowing | 11.69781 ✓ |
| real file, columns reordered (CSV) / time+flux only | `--cols`, `--flag-good all`, error fill | 5.35792 ✓ |
| real file | `--detrend sine`, `--window-days 0.25/0.75`, `--mask`, `--force-factor 0.5/2` | 5.35792 / 5.35792 / 5.35748 / weak residual 3.12 / 2.67896 / 10.71584 ✓ |

Functional testing was not done with fresh agents: this session's instructions forbid spawning other agents or `claude -p`, so the walkthrough above was done in-session.
