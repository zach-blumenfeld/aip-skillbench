# box-least-squares — AIP conversion notes

Source: `vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills/box-least-squares/SKILL.md`
Canonical original retained at `source/SKILL.original.md`.

## Schema choice

Reused `procedure.schema.json` (bundled here as `source/procedure.schema.json`).
The skill is a structured BLS workflow — discrete steps in a typical order
(install astropy → prepare data → choose autopower vs power → pick objective
→ extract peak → compute_stats validation → phase-fold inspection), signal-to-
action decisions for result interpretation and troubleshooting (no clear peak,
2x/0.5x aliasing, high odd-even mismatch), and explicit anti-patterns. That
maps cleanly onto `purpose / trigger_when / steps / decisions /
search_shortcuts / scenarios / anti_patterns`.

## Mapping notes

- **Overview / Basic Usage** → `steps.prepare-data`, `steps.build-bls-object`,
  `steps.run-autopower` plus a `scenarios` entry for the minimal end-to-end
  example.
- **autopower vs power (Custom Period Grid)** → `steps.choose-grid-method`
  with a `decisions` row, plus a `search_shortcuts` block summarising when to
  use each.
- **Objective Functions (likelihood vs snr)** → `steps.pick-objective` with a
  `decisions` row covering when correlated noise pushes you to `snr`.
- **Peak Statistics for Validation / Validation criteria** →
  `steps.compute-stats` and `steps.validate-candidate`, with thresholds
  surfaced both in `decisions` and a `search_shortcuts` block for quick
  lookup.
- **Period Grid Sensitivity / autoperiod** → `steps.refine-grid` plus a
  `scenarios` entry showing the `autoperiod()` → `power()` pattern.
- **Comparing BLS Results (top N peaks)** → `scenarios` entry — concrete code
  shape preserved without re-encoding as another step.
- **Phase-Folded Light Curve** → `steps.phase-fold-results` plus a `scenarios`
  entry for the fold-plot pattern.
- **BLS vs TLS / When to Use BLS / When to Use Lomb-Scargle** → `decisions`
  rows (one each) plus a `do_not_use_when` entry for non-transit periodic
  signals where Lomb-Scargle is the better tool.
- **Integration with Preprocessing / Key Considerations** → distributed across
  `steps` (the order: quality → outliers → detrend → BLS → validate) and
  `anti_patterns` (over-aggressive preprocessing). Not encoded as a separate
  workflow step list since it duplicates the procedure ordering.
- **Common Issues (no clear peak, 2x/0.5x period, odd-even mismatch)** →
  `decisions` rows for recovery actions and `anti_patterns` for the mistakes
  to avoid in the first place.
- **References / Dependencies / Installation** → `search_shortcuts`
  ("Dependencies", "Official documentation", "Key papers", "Related
  resources") plus a `steps.install` for the install step. The `pip install`
  line appears twice in the source; deduplicated.

## Deliberate non-duplications

- "Integration with Preprocessing" workflow list overlaps with the step
  ordering; not re-encoded as its own field.
- The `pip install astropy` snippet appears twice in the source (Installation
  and Dependencies); kept once in `search_shortcuts.Dependencies` and once
  in `steps.install`.
- "When to Use BLS / TLS / Lomb-Scargle" sections overlap with the BLS-vs-TLS
  Pros/Cons block; consolidated into `decisions` rows plus the
  `do_not_use_when` entry rather than repeated as a separate field.
