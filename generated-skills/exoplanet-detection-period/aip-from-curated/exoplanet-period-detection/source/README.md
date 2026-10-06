# source/ provenance and compilation notes

## What this contains

Verbatim copies of the five curated Agent Skills this AIP skill was compiled
from, exactly as supplied under `./inputs/skills/`:

- `exoplanet-workflows/` — pipeline-level guidance and method-selection advice.
- `light-curve-preprocessing/` — quality flags, sigma clipping, Savitzky-Golay
  flattening, pipeline ordering.
- `lomb-scargle-periodogram/` — Lomb-Scargle periodogram, period range guidance,
  comparison to TLS/BLS.
- `box-least-squares/` — Astropy BLS periodogram, autopower/power, objective
  functions, odd-even validation.
- `transit-least-squares/` — TLS algorithm, flux_err requirement, broad+refine
  pattern, SDE/SNR thresholds, transit masking.

The compiled skill lives one directory up (`../SKILL.md` plus `../scripts/` and
`../references/`). Nothing in `source/` is loaded by the runtime — it is the
canonical human-readable material the body was synthesized from.

## Target task

One file: a plain-text TESS light curve with four whitespace-delimited columns
(time MJD, flux relative, quality flag, flux error) and `#` comment headers,
as described by `../../inputs/environment/MANIFEST.md`. The container
(`../../inputs/environment/Dockerfile`) provides numpy 1.26, scipy 1.13,
astropy 6.0, transitleastsquares 1.32, and lightkurve 2.4 on Python 3.12.

## Step-kind choices

Walked through the Best Practices order (script → decision → client task):

| Step             | Kind       | Why                                                                                                                                  |
|------------------|------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `preprocess`     | execution  | Pure deterministic numeric transforms: load, mask on flag==0, 5-sigma clip, Savitzky-Golay flatten. Lookup rules are trivially scriptable. |
| `broad-search`   | execution  | TLS call is deterministic given the data; period range (0.5 d to min(15, baseline/2)) and SDE→strength lookup are both fixed rules. |
| `by-strength`    | router     | Branches on the `strength` label produced by the script. A router keeps the branch cheap and inspectable; no judgment is needed because the SDE thresholds (>=9 very_strong, >=6 strong, <6 weak) come straight from the source material. |
| `refine-search`  | execution  | Narrow TLS re-search is parameterised entirely by the candidate period (±5%); no judgment required. |
| `end`            | end        | Returns the final state shape: period, uncertainty, strength label, SDE, SNR, plus T0/duration/depth from the broad search for follow-up characterization. |

No `decision` or `client_task` steps are needed: every judgment the source
material prescribes (strength tiers, period-range selection, refinement
window) collapses to a fixed rule the scripts encode. Keeping judgment out of
decision steps avoids the "over-restriction" failure mode when the agent would
otherwise have reasoned correctly on the same signal.

## Pipeline flow

```
light_curve_path ─▶ preprocess ─▶ broad-search ─┬─▶ (strong|very_strong) ─▶ refine-search ─▶ end
                                                └─▶ (weak) ───────────────────────────────▶ end
```

`broad-search` pre-populates `period_days`, `period_uncertainty_days`,
`final_sde`, `final_snr` with the broad-search values so the weak branch
reaches `end` with a complete answer; `refine-search` overwrites those four
keys on the strong branch.

## Deliberate-drop log

Material in the five source SKILL.mds that was intentionally not carried into
the compiled body. Rules, thresholds, lookups, branching, and the context
needed to apply them are **never** deliberately dropped — anything in that
category below would be a bug. These are all background, redundancy, or
alternatives that would double the body size without changing behaviour.

### From `exoplanet-workflows/SKILL.md`

- **General pipeline overview (loading → QC → preprocessing → search → validation → refinement).**
  Redundant: the AIP step graph *is* that pipeline, in executable form.
- **"Which period search algorithm?" prose (TLS vs Lomb-Scargle vs BLS).**
  Captured as a hard choice: this pipeline runs TLS. The alternatives and the
  rationale are preserved in `source/exoplanet-workflows/SKILL.md`; the AIP
  purpose statement names TLS and the trade-off is referenced from the body.
- **Expected transit depths by planet class (hot Jupiter 1–3%, Earth 0.01–0.1%).**
  Context only — not consumed by any script and not needed to pick a parameter.
  Lives in the source for an agent that wants it.
- **Period range guidelines by target type (hot Jupiter 0.5–10 d, habitable
  zone 200–400 d, …).**
  The scripted range (0.5 d → min(15 d, baseline/2)) covers hot Jupiters, warm
  planets, and anything with ≥2 transits in a typical TESS single-sector
  baseline (~27 d). Longer-period search would be unverifiable (<2 transits).
  Full ranges remain in the source for an agent targeting non-TESS cadences.
- **Multi-planet strategy (mask-and-repeat).**
  Explicitly scoped out in `do_not_use_when`. A multi-planet variant would
  need a loop over `transit_mask`, which belongs in a separate skill.
- **Issue log ("No significant detection", "Period 2x/0.5x expected", "flux_err
  required").**
  The relevant rules are either enforced by the scripts (flux_err always
  passed) or captured as anti-patterns in the body (period aliasing).

### From `light-curve-preprocessing/SKILL.md`

- **Alternative flag conventions (`flag != 0` means good in some exports).**
  The MANIFEST documents a standard TESS file; `preprocess.py` hard-codes
  `flag == 0 is good`. The variant convention stays in the source for a
  future task that explicitly flags a non-standard file.
- **Lightkurve-based preprocessing idioms (`lc.remove_outliers`,
  `lc.flatten(window_length=…)`).**
  Replaced by direct numpy + scipy (`np.loadtxt`, median/std clip, scipy
  `savgol_filter`) to avoid a lightkurve dependency on the local runner
  (the container has lightkurve; the local Python 3.14 harness does not).
  The algorithm (sigma clip + Savitzky-Golay) is identical.
- **Iterative sine-fitting detrender.**
  Explicitly warned-against in the source for transit searches ("removes
  periodic signals") — not used.
- **`view='period'` vs `view='frequency'` plotting detail.**
  No plotting in the pipeline; it is a report-time concern.
- **Second-pass outlier removal.**
  Omitted for simplicity; one 5-sigma pass before flatten is sufficient for
  the TESS SPOC-style curve the MANIFEST describes.

### From `lomb-scargle-periodogram/SKILL.md`

- **Entire Lomb-Scargle usage.**
  TLS is the chosen algorithm (purpose statement, anti-pattern); LS is
  preserved in the source as context for method selection.

### From `box-least-squares/SKILL.md`

- **Entire BLS usage, `autopower`/`power`, `compute_stats()`, objective
  functions.**
  TLS is strictly more sensitive for the transit-shaped signal this skill
  targets (per the source material's own TLS-vs-BLS comparison). BLS is
  preserved in the source as a fallback method; a BLS variant would be its
  own skill.
- **Multiple-duration grid sweep.**
  TLS searches the duration grid internally; no explicit duration array needed.

### From `transit-least-squares/SKILL.md`

- **Transit masking for second-planet search (`transit_mask`).**
  Explicitly scoped out in `do_not_use_when` (single-candidate skill).
- **`oversampling_factor`, `duration_grid_step`, `T0_fit_margin` tuning
  guidance.**
  Only `oversampling_factor=5` is used, in the refine step. The other
  parameters stay at defaults; their descriptions remain in the source.
- **Model-light-curve / phase-folded plotting examples.**
  Reporting concern, not computation.
- **"flux_err is required" warning.**
  Enforced in the scripts (flux_err is always loaded and passed); echoed
  as an anti-pattern in the body.
- **SDE/SNR thresholds (>=6 candidate, >=9 strong, <6 weak).**
  Captured as a hard script lookup inside `broad_search.py` and used by the
  router.
- **Advanced-parameter duplicate paragraph** (the source lists
  `oversampling_factor` / `duration_grid_step` / `T0_fit_margin` twice,
  under two near-identical "Advanced" headings).
  Treated as one piece of guidance; the second copy is a prose-level
  duplicate.
