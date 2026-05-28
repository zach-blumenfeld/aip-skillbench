# transit-least-squares — AIP conversion notes

Source: `vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills/transit-least-squares/SKILL.md`
Canonical original retained at `source/SKILL.original.md`.

## Schema choice

Reused `procedure.schema.json` (bundled here as `source/procedure.schema.json`).
The skill is a structured TLS workflow — discrete steps with a typical order
(install → build TLS object → run power search → extract / interpret results →
phase-fold → mask + repeat for multi-planet), signal-to-action decisions for
result interpretation and troubleshooting, and a list of common mistakes
("flux_err is required", aliased periods, low SDE). That maps cleanly onto
`purpose / trigger_when / steps / decisions / search_shortcuts / scenarios /
anti_patterns`.

## Mapping notes

- **Overview / Basic Usage / Example with explicit period range** → `steps`
  (`build-tls-object`, `run-power-search`, `extract-results`). Code-shape and
  parameter snippets are captured as `scenarios` (with explicit period range,
  oversampling tuning) so the body stays compact while the procedure remains
  worked.
- **Installation / Dependencies** → `steps.install` plus a `search_shortcuts`
  Dependencies entry. Two source mentions deduplicated.
- **Period Refinement Strategy + Advanced Options + Advanced Parameters** →
  `steps.refine-period` and `scenarios` for the broad-then-narrow workflow,
  plus a `search_shortcuts` entry capturing typical refinement windows and
  advanced parameter knobs (`oversampling_factor`, `duration_grid_step`,
  `T0_fit_margin`). The two source headings ("Advanced Options" and "Advanced
  Parameters") are near-duplicates and are merged into one shortcut block.
- **Phase-Folding** → `steps.phase-fold-results` plus a `scenarios` entry
  showing the folded-data plot pattern.
- **Transit Masking / Multiple Planet Search Strategy** → `steps.mask-and-iterate`
  plus a `scenarios` entry for the masked re-search pattern.
- **Interpreting Results (SDE, SNR, warnings)** → `decisions` (SDE/SNR
  thresholds, "X of Y transits without data" warning → check `period * 2`) and
  a `search_shortcuts` block listing the thresholds for quick lookup.
- **Model Light Curve** → `steps.inspect-model` plus a small `scenarios` entry
  for the model-overlay plot.
- **Workflow Considerations / Typical Parameter Ranges** → distributed across
  `steps` (the order: outliers → flatten → search → refine → validate),
  `search_shortcuts` (typical parameter ranges), and `decisions` (refinement
  trigger). Not encoded as a separate workflow step list since it duplicates
  the procedure.
- **References** → `search_shortcuts` "Official documentation" category.
- **When to Use TLS vs. Lomb-Scargle** → `decisions` (one row each) plus a
  `do_not_use_when` entry for non-transit periodic signals where Lomb-Scargle
  is the better tool.
- **Common Issues (flux_err, 2x/0.5x period, low SDE)** → `decisions` for the
  recovery actions and `anti_patterns` for the mistakes to avoid in the first
  place.

## Deliberate non-duplications

- Workflow Considerations and Multiple Planet Search Strategy overlap with the
  step list; not re-encoded.
- "Advanced Options" and "Advanced Parameters" merged — same knobs described
  twice in the source.
- The `pip install` line is repeated twice in the source (Installation and
  Dependencies); kept once in `search_shortcuts.Dependencies` and one
  `steps.install`.
