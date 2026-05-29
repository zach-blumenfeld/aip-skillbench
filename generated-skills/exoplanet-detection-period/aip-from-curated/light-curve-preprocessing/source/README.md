# Source notes — light-curve-preprocessing (AIP)

## Origin
Compiled from `source/SKILL.original.md` (the curated freeform Markdown skill
shipped with the SkillsBench `exoplanet-detection-period` task) into the AIP
`procedure` schema bundled at `source/procedure.schema.json`.

## Schema choice
`procedure.schema.json` — the preprocessing workflow IS a structured procedure
with ordered, partly-parallelizable steps: inspect input → choose parameters →
filter quality flags → remove outliers → detrend → optional second-pass /
sine-fit → visual check. No need to draft a new schema.

## Script vs. prose decisions
The original Markdown is a recipe doc with embedded code snippets. The
deterministic / mechanical core was lifted into scripts; data-dependent
judgment calls were kept as prose steps.

- **scripts/preprocess.py** — full canonical pipeline (load TXT → quality
  filter → sigma-clip → flatten). Parameterized over sigma, window length,
  flag convention, and stage skips. Deterministic; this is the workhorse.
- **scripts/sine_fit_detrend.py** — iterative sine-fit detrender for high-
  frequency stellar variability. Self-contained and destructive; isolated
  in its own script so the agent must opt in.
- **scripts/plot_lc.py** — quick PNG plot for visual verification.

- **inspect-input** (prose) — judging column layout / units / flag convention
  is interpretation, not lookup. Wrong call → wrong filter direction.
- **choose-parameters** (prose) — sigma and window-length selection trades
  off transit preservation vs. trend removal; depends on physical priors
  about the target.
- **visual-check** (prose) — "did flatten() eat my transit?" is a judgment
  call from a plot.
- **optional-second-pass** (prose) — re-running preprocess.py with different
  knobs; no new script needed.

## Content mapping (original → AIP body)
- Outlier-removal section → `run-pipeline` step (sigma param) and prose
  notes on aggressive/conservative thresholds in `choose-parameters`.
- Lightkurve `flatten()` discussion → `run-pipeline` step (window-length
  param) and prose notes on window selection.
- Iterative sine fitting → `optional-sine-detrend` step + script.
- Quality-flag convention section (good_is_zero vs. bad_is_zero) → captured
  in both the `flag-convention` param of preprocess.py and as a gotcha in
  `anti_patterns`.
- "Key Steps (Order Matters!)" → the step ordering and an `anti_patterns`
  entry against reordering.
- Best-practices list → folded into `anti_patterns` and the prose of
  `choose-parameters` / `visual-check`.
- Visualization section → `visual-check` step + `scripts/plot_lc.py`.
- Dependencies list → captured in `compatibility` frontmatter.
- External Lightkurve doc links → preserved in `search_shortcuts`.

## Deliberate drops
- The duplicated "Preprocessing for Exoplanet Detection" sub-section: it
  restates outlier-then-flatten advice already covered by `run-pipeline`
  and `anti_patterns`. Folded into existing content rather than repeated.
- The "manual outlier removal" numpy snippet: redundant with the
  lightkurve-backed sigma-clip already wired into preprocess.py. Keeping
  both would invite the agent to roll its own and skip the script.
