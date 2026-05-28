# light-curve-preprocessing — AIP conversion notes

Source: `vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills/light-curve-preprocessing/SKILL.md`
Canonical original retained at `source/SKILL.original.md`.

## Schema choice

Reused `procedure.schema.json` (bundled here as `source/procedure.schema.json`).
The skill is a structured preprocessing workflow — discrete steps with a
required order, signal-to-action decisions for parameter selection, and a list
of common mistakes. That maps cleanly onto `purpose / trigger_when / steps /
decisions / search_shortcuts / anti_patterns`.

## Mapping notes

- **Overview / "Key Steps (Order Matters!)"** → `steps` (quality-flag filtering,
  outlier removal, trend removal, optional second-pass outlier removal,
  visualize/verify). Order is encoded by list position.
- **Outlier removal (lightkurve + manual)** → `steps.outlier-removal` plus a
  `search_shortcuts` entry for sigma value selection.
- **Flattening / iterative sine-fitting** → `steps.detrend` plus an
  `anti_patterns` entry warning that sine fitting removes periodic signals.
- **Quality-flag conventions** → `steps.quality-control` plus a `decisions`
  entry on the flag==0 ambiguity.
- **Parameter Selection** → `decisions` entries (sigma, window length, two
  passes) and a `search_shortcuts` entry summarising the parameter tables.
- **Important Principles + Best Practices** → `anti_patterns` (concrete
  corrections) and `decisions` (action-shaped guidance).
- **Visualization** → `steps.verify-visually`.
- **Dependencies / References** → `search_shortcuts` (Dependencies, Official
  documentation).
- **Preprocessing for Exoplanet Detection** → not a separate step; it's
  guidance that already lives in `outlier-removal`, `detrend`, and the
  anti_patterns. Recorded here as a deliberate non-duplication.
