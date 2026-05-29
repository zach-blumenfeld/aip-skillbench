# Source notes — lomb-scargle-periodogram (AIP from curated)

## Origin
Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills/lomb-scargle-periodogram/SKILL.md`
into AIP format. Original copied verbatim to `source/SKILL.md` for traceability.

## Schema choice
`procedure.schema.json` (existing AIP schema, reused).

Why: the curated SKILL.md is a step-by-step recipe — load light curve, choose a
period range, compute Lomb-Scargle, interpret peaks, optionally fit a model.
That is the canonical shape `procedure` was designed for; no new schema needed.

## Script choice
One script, `scripts/run_lomb_scargle.py`. Backs the `compute-periodogram` step.

- **Deterministic and tabular** — wraps `lightkurve.LightCurve.to_periodogram()`,
  extracts strongest period and the top-N peaks for harmonic inspection. The
  agent reads top-N back as JSON, then reasons about the fundamental.
- **Why not script `select-period-range`** — the table is a lookup, but the
  agent must *judge* which science case applies from the user's prompt and
  the data context (TESS vs Kepler, target type, prior knowledge). That
  judgement step is left as prose; the lookup table lives in `search_shortcuts`.
- **Why not script `interpret-peaks`** — harmonic vs alias vs true-period
  reasoning depends on power ratios, integer-fraction relationships, and
  domain priors. A script that emits the top-N peaks gives the agent the
  data it needs without prescribing an answer.

## Completeness mapping (source → body)

| Source content                              | Disposition                                   |
|---------------------------------------------|-----------------------------------------------|
| "What LS is" overview                        | Mapped → `purpose`                            |
| Basic Usage code snippet                     | Mapped → `compute-periodogram` step + script  |
| Plotting (`view='period'` gotcha)            | Mapped → `plot-periodogram` step + anti-pattern |
| Period range table (4 science cases)         | Mapped → `search_shortcuts`                   |
| Interpreting results (harmonics, aliasing)   | Mapped → `interpret-peaks` step + anti-patterns |
| Model fitting code                           | Mapped → `optionally-fit-model` step          |
| Dependencies line                            | Mapped → frontmatter `compatibility`          |
| References (lightkurve docs)                 | Mapped → `purpose` (lightkurve) — URLs omitted to keep body lean; trivially recoverable |
| "When to use vs other methods" (TLS, BLS)    | Mapped → `do_not_use_when` + `integrations`   |

## Cross-skill notes
This skill is one of five under the parent task. It composes with:
- `light-curve-preprocessing` (filter, sigma-clip, flatten — runs *before* this)
- `transit-least-squares` (more sensitive than LS for box-shaped transits — usually runs *after* this for exoplanet work)
- `box-least-squares` (alternative transit search)
- `exoplanet-workflows` (the umbrella playbook for end-to-end exoplanet period detection)
