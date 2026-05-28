# Lomb-Scargle Periodogram — AIP conversion notes

Converted from the curated freeform-markdown skill at
`vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills/lomb-scargle-periodogram/SKILL.md`
to the AIP `procedure` schema.

## Schema choice

`procedure.schema.json` — the source is a multi-step periodogram workflow
(build → search → inspect → interpret → optionally fit a model), with
trigger conditions, signal-to-action interpretation guidance, and explicit
"when to use this vs. other methods." Maps cleanly to a Procedure.

## Source → body mapping

- **Overview** → `purpose`.
- **Basic Usage with Lightkurve**, **Plotting Periodograms**, **Period Range Selection**, **Model Fitting** → `steps` (build-light-curve, compute-periodogram, plot-periodogram, model-fit, etc.).
- **`view='period'` gotcha** → captured in the plot step + `anti_patterns`.
- **Period Range Selection** science-case table → `search_shortcuts` (Period ranges by science case).
- **Interpreting Results / Common Patterns** (harmonics, aliasing) → `decisions` and `anti_patterns`.
- **Dependencies** → `search_shortcuts` (Dependencies).
- **References** (URLs) → `search_shortcuts` (Official documentation).
- **When to Use This vs. Other Methods** → `do_not_use_when` plus `integrations` (TLS, BLS).

Nothing was deliberately dropped; every distinct piece of source content
maps to a field in the body.

## Name

Preserved verbatim from the source skill: `lomb-scargle-periodogram`.
The task's mounted-skill name must match.
