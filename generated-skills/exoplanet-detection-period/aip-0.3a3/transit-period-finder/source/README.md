# transit-period-finder: source, provenance and compilation notes

## Intent

A single AIP procedure skill that lets an autonomous agent go from a raw light-curve text file
(time, normalized flux, quality flag, flux error) with strong stellar variability to one
vetted, model-refined transiting-planet period, written to a file at the requested rounding.
It compiles five curated, overlapping Agent Skills that each describe one part of that workflow.

## Provenance

All files below are verbatim copies of the curated inputs (checked with `diff -r`):

| Path in source/ | Origin | Role |
|---|---|---|
| `exoplanet-workflows/SKILL.md` | curated skill `exoplanet-workflows` | Pipeline stages, method choice, validation thresholds, depths and periods, best practices |
| `light-curve-preprocessing/SKILL.md` | curated skill `light-curve-preprocessing` | Flag conventions, outlier removal, `flatten()` windows, iterative sine fitting |
| `lomb-scargle-periodogram/SKILL.md` | curated skill `lomb-scargle-periodogram` | Lomb-Scargle usage, period ranges, harmonics and aliases, sinusoid model |
| `transit-least-squares/SKILL.md` | curated skill `transit-least-squares` | TLS API, flux_err requirement, refinement, SDE/SNR, masking, multi-planet |
| `box-least-squares/SKILL.md` | curated skill `box-least-squares` | BLS API, objectives, `compute_stats` validation, grid sensitivity, BLS vs TLS |
| `procedure.schema.json` | aip skill `assets/aip-schemas/procedure.schema.json` (v0.3a3) | The schema the SKILL.md body validates against (reused, not new) |

The curated skills contain only SKILL.md files: no scripts, references or assets.
Other domain context came from the task statement (instruction.md), the container Dockerfile
(the package versions pinned below) and the real input file, which was inspected and
functional-tested in a scratch dir that is not part of this skill.

## Schema choice

`procedure.schema.json` was reused. The task is a linear execution graph with one judgement
branch (vetting), and that schema has every field needed: steps with
script/inputs/outputs/one_of, modes, scenarios, anti_patterns, do_not_use_when and
scope_and_approval. No schema gap was found, so no new schema was drafted.

## Component-kind choices (script vs prose vs reference)

| Content | Kind | Why |
|---|---|---|
| Loading, flag filter, NaN/error repair, normalisation | script (`prepare`, `basic_clean`) | Deterministic. Column order and flag convention are CLI flags, so another instance or format needs no code edits |
| Flag-convention decision | prose (choose-preprocessing), with numeric support from `inspect` (per-subset scatter) | The task statement may define it. Otherwise it is a judgement from the evidence, which is what the source says to do ("check which approach gives cleaner results") |
| Lomb-Scargle variability period, recommended window (P_rot/4 clamped to [0.25, 0.75] d) | script | A numeric rule. The source gives only the qualitative rule "longer than the transit, shorter than the rotation" plus cadence-count tables. A time-based rule generalises across cadences |
| Iterative sine fitting (pre-whitening) | script, default 10 terms, stops when amplitude < median flux error | Numeric. Functional testing showed it was needed: on a synthetic 0.9 d rotator with a strong harmonic, flatten alone let TLS lock onto the rotation |
| Outlier clipping | script: clip against the local trend, 3σ high; low only if > 10σ and isolated | Numeric. The source's symmetric `remove_outliers(sigma=3)` on raw flux clips variability troughs, and a lower 3σ clip after flattening deletes transit points. Adapted, not copied |
| TLS search, BLS cross-check at 3 windows, alias and validation statistics, warning flags | script (`search`) | Thresholds (SDE 6/9, SNR 7, odd/even 3σ, 2% rotation proximity) are fixed rules. Encoded as flags |
| Accepting a candidate or choosing an alias/rerun | prose `vet-candidate` with `one_of` | Weighing several flags against each other is judgement. The flags are raw material, not a decision table |
| Period refinement | script (`refine`): masked re-flatten, batman fit, dense-BLS fallback, reliability gate | Precision matters at 5 decimals. TLS's grid period was about 0.0015 d off the fit (≈5σ) on the real data; a narrow-window TLS rerun returned the identical grid value |
| Answer-file format check, reporting | prose `check-answer` | Trivial, task-dependent |
| API details, thresholds tables, troubleshooting, depth/period guidelines, BLS vs TLS vs LS | `references/methods.md` (on demand) | Keeps the body under budget. Loaded only when vetting is unclear or custom code is needed |

One script with subcommands rather than several files: they share the loader, cleaner and
flatten code.

## Corrections to the sources (found while testing against the container's versions)

1. `BoxLeastSquares.compute_stats` (astropy 6.0.1) has no `depth_snr`, `depth_err` or
   `transit_count` keys, which the BLS source uses. The source code raises KeyError. The
   replacements are in methods.md, an anti-pattern, and `bls_stats()`.
2. TLS 1.32 defaults are `oversampling_factor=3` and `T0_fit_margin=0.01` (a fraction of the
   duration, capped at 0.1). The TLS source says 1 and 5. Corrected in methods.md.
3. TLS needs a `__main__` guard (multiprocessing spawn). Not in the sources; found when an
   unguarded test crashed.
4. Symmetric 3σ clipping on raw flux and a post-flatten lower clip are unsafe for transits;
   see the table above.

## Completeness check (source content → compiled skill)

Legend: **M** = mapped (location), **A** = mapped with adaptation, **D** = deliberate drop.

### exoplanet-workflows
- Overview and the 6 key stages → M: steps read-task…check-answer.
- Critical decisions (what to preprocess, which algorithm, period range, when to refine) → M:
  choose-preprocessing, search, refine; methods.md "Choosing a method".
- TLS / Lomb-Scargle / BLS use-when, advantages, disadvantages → M: methods.md table; do_not_use_when (rotation-only goal).
- Validation: SDE > 9 / > 6, SNR > 7, warning signs, how to validate → M: vet-candidate, search flags, methods.md thresholds.
- Multi-planet strategy and `transit_mask` → M: modes.additional-planets, `search --mask`, methods.md.
- Common issues (low SDE, 2×/0.5× period, flux_err required, preprocessing-dependent results) → M: vet-candidate one_of, anti-patterns, methods.md troubleshooting.
- Expected transit depths; period-range guidelines → M: methods.md.
- Best practices 1–8: flux_err (M anti-pattern); visualize each step (A, see D1); flag convention (M choose-preprocessing); sigma 3 then 5 (A, clipping against the trend); refine (M refine); validate (M vet); data gaps (M empty-transit flag); document the workflow (M: JSON reports in the work dir).
- References, lightkurve tutorial sections, papers → M: methods.md Further reading.
- Dependencies (`pip install …`) → D2.

### light-curve-preprocessing
- Lightkurve `remove_outliers` with sigma levels; manual median/std clipping → A: script `clip_outliers`; the API and sigma levels are in methods.md.
- `flatten(window_length)` with window tables; Savitzky-Golay note → M: script `flatten`; tables in methods.md.
- Iterative sine fitting and its warning → A: script `prewhiten` (amplitude-stopped, not a blind 50 iterations); the warning is an anti-pattern.
- Quality-flag conventions (zero good vs non-zero good, verify) → M: `--flag-good`, inspect per-subset scatter, choose-preprocessing, scenario 3.
- Pipeline order (flags → outliers → trend → optional second pass) → M: search pipeline. The second pass is the masked re-clip in refine.
- Principles (flux_err, preserve shapes, don't over-process, verify visually) → M or A: anti-patterns; visual verification per D1.
- Parameter selection (sigma ranges, window between transit and rotation, two passes) → M: methods.md; window rule in script.
- Visualizing results (`lc.plot()`) → D1. Dependencies → D2. References → M.

### lomb-scargle-periodogram
- Basic usage, `period_at_max_power`, `max_power` → M: methods.md; script `ls_rotation` (astropy LombScargle, same algorithm).
- Plotting with `view='period'` → M: methods.md (D1 for actually plotting).
- Period ranges by phenomenon → M: methods.md.
- Interpreting power, harmonics, aliases → M: vet-candidate (P/2, 2P, P_rot proximity flags).
- Model fitting with `pg.model` → A: `prewhiten` uses the equivalent `LombScargle.model`.
- When to use vs TLS/BLS → M: methods.md table.

### transit-least-squares
- Installation → D2. Basic usage with mandatory flux_err; result attributes → M: script `run_tls`; methods.md; anti-pattern.
- Explicit period range → M: `--period-min/--period-max` (default 0.5 d to baseline/2).
- Period refinement strategy (±2–10% narrow search) → A: refine uses a transit-model fit plus dense BLS, which is more precise. The narrow-TLS idea and its limits are in methods.md.
- Advanced parameters (oversampling_factor, duration_grid_step, T0_fit_margin) → M with corrected defaults: methods.md.
- Phase-folding attributes; model light curve → M: methods.md (D1 for plotting).
- Transit masking for a second planet → M: `--mask`, modes.
- SDE and SNR interpretation; "transits without data" warning → M: flags, vet-candidate.
- Workflow considerations, typical parameter ranges, multi-planet strategy → M: steps, modes.
- Common issues → M: troubleshooting, one_of.

### box-least-squares
- Overview, key parameters, installation → M / D2.
- Basic usage, autopower vs power, autoperiod, period grid warning → M: methods.md; the script builds its own phase-drift-limited frequency grid.
- Objectives (likelihood vs SNR) → M: methods.md. The script uses snr for the search and likelihood for the dense refinement.
- Complete example, peak extraction → M: methods.md.
- `compute_stats` validation and criteria → A: corrected keys (see Corrections 1); criteria in vet-candidate.
- Comparing the top 5 peaks → M: `top_independent_peaks` (TLS, harmonics removed); BLS top-5 snippet in methods.md.
- Phase-folded light curve → M: methods.md fold formula.
- BLS vs TLS pros/cons and recommendation "try both" → M: methods.md table; search runs both.
- Integration with preprocessing, key considerations → M: search pipeline.
- Common issues (no clear peak, 2×/0.5×, odd/even mismatch) → M: troubleshooting, one_of.
- Dependencies → D2. References and papers → M. "When to use BLS/TLS/LS" → M.

### Deliberate drops
- **D1 Plots (`plt.show()`, `lc.plot()`, `pg.plot()`).** The consumer is an autonomous agent in
  a headless container. Visual checks are replaced by numeric ones the agent can read:
  per-transit depths, odd/even, P/2 and 2P stats, BLS agreement across windows, reduced χ².
  The plotting API is still listed in methods.md for agents that want an image.
- **D2 `pip install` lines.** The container already has every package (Dockerfile). Installing
  is unnecessary and may have no network. Covered by the `compatibility` frontmatter.
- **D3 Repeated content.** The five sources repeat the SDE/SNR thresholds, the 2×/0.5×
  period issue, the flux_err warning and the BLS/TLS/LS comparison four or five times. Each
  appears once in the compiled skill.
- **D4 The "flag=0 is BAD" code snippet as a default.** It is kept as an option
  (`--flag-good nonzero`) and is not presented as an equal default, following the provide-defaults rule.

## Functional-test summary (done in-session, scratch dir outside the skill)

Every command was run exactly as the body gives it, with a Python 3.12 environment pinned to
the Dockerfile versions:
- Real input file: inspect → search (TLS SDE ≈ 21, 4 transits, every BLS window agrees) →
  refine (batman fit, agrees with dense BLS, reliable) → a one-line 5-decimal answer file.
  The result is stable to about 3e-5 d across windows of 0.25 to 0.35 d, with and without
  pre-whitening.
- Synthetic instances with known periods (not bundled): 3.71 d planet on a 2.3 d rotator, 8.90 d
  on a 0.9 d rotator with a harmonic, and 2.19 d with inverted flags. All recovered within
  1.2σ of the truth once the right branch was taken.
- Branches reached: masked second-planet search (single event correctly flagged); wrong flag
  convention (exit when no points survive; flagged unreliable otherwise); manual
  --period/--t0/--duration; a wrong candidate (flagged unreliable); batman unavailable
  (dense-BLS fallback); no error column (`--cols 0,1,2,-1`); --window-days override.
