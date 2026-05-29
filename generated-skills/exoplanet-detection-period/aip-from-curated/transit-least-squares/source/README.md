# Source notes — transit-least-squares (AIP from curated)

## Origin
Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills/transit-least-squares/SKILL.md`
into AIP format. Original copied verbatim to `source/SKILL.md` for traceability.

## Schema choice
`procedure.schema.json` (existing AIP schema, reused — same choice as the sibling
`lomb-scargle-periodogram` skill).

Why: the curated SKILL.md is a step-by-step recipe — verify preprocessing,
broad TLS search, inspect SDE/SNR, refine the period in a narrow window, then
optionally mask transits and search for additional planets. That is the
canonical shape `procedure` was designed for; no new schema needed.

## Script choices

Two scripts:

1. `scripts/run_tls.py` — backs both the broad-search and the refinement
   steps. Wraps `transitleastsquares(...).power(...)` with the canonical
   defaults from the source SKILL.md.
   - **Deterministic and tabular**: load columns → construct TLS object →
     call `.power()` → emit scalars as JSON.
   - **Encodes the "always include flux_err" rule**: `--err-col` defaults to
     column 2; `--no-err` is the explicit opt-out and warns to stderr.
   - **Refinement is a flag, not a separate script**: `--refine-around <P>`
     plus `--refine-pct` (default 0.05) implements the canonical "±5% around
     the candidate" pattern from the curated SKILL.md without duplicating the
     load-and-run plumbing.
   - **Surfaces aliasing risk**: emits `transits_in_data_gaps` so the agent
     can act on the "true period may be twice the given period" warning in
     code rather than only as prose.

2. `scripts/mask_transit.py` — backs the "search for additional planets" step.
   Wraps `transitleastsquares.transit_mask(...)` and writes the masked light
   curve to a CSV the agent can re-feed to `run_tls.py`.

## Why some steps stay as prose

- `verify-preprocessing` — the decision is **judgement** ("is this curve
  flat enough?"), not a fixed rule the agent could mechanically execute. The
  schema describes the expected handoff; the actual cleanup belongs to the
  `light-curve-preprocessing` skill.
- `assess-candidate` — interpreting SDE/SNR thresholds against the
  particular signal involves reading the candidate's context (e.g., is a low
  SDE caused by over-aggressive flattening?). A script that returned a
  boolean would hide that reasoning. The thresholds (SDE > 6, SDE > 9,
  SNR > 7) appear as prose in the body so the agent can apply them with
  domain awareness.
- `decide-multi-planet-search` — optional follow-up; whether to run depends
  on the task goal. The agent reasons whether to invoke `mask_transit.py`.

## Completeness mapping (source → body)

| Source content                                       | Disposition                                                              |
|------------------------------------------------------|--------------------------------------------------------------------------|
| "What TLS is" overview                                | Mapped → `purpose`                                                       |
| Installation / Dependencies                           | Mapped → frontmatter `compatibility`                                     |
| Basic Usage code (flux_err critical)                  | Mapped → `run-broad-search` step + `run_tls.py` (defaults to err-col=2)  |
| Example with explicit period range                    | Mapped → `refine-period` step + `--min-period`/`--max-period` flags      |
| Period Refinement Strategy (±5%)                      | Mapped → `refine-period` step + `--refine-around` flag                   |
| Advanced Options (oversampling, duration_grid_step…)  | Mapped → `anti_patterns` ("don't tune blindly") + script defaults; full param list deliberately dropped as low-value vs body-token cost |
| Phase-Folding code                                    | Deliberately dropped → folded arrays available via TLS object; reproducible from period+T0 and not used by the period-detection task. Recorded here. |
| Transit Masking                                       | Mapped → `mask-and-search-next` step + `mask_transit.py`                 |
| SDE interpretation (>6 candidate, >9 strong)          | Mapped → `assess-candidate` step prose + `anti_patterns`                 |
| SNR interpretation (>7 reliable)                      | Mapped → `assess-candidate` step prose                                   |
| "Transits without data" warning → period * 2 aliasing | Mapped → `assess-candidate` prose + `anti_patterns` + script's `transits_in_data_gaps` output |
| Model Light Curve code                                | Deliberately dropped → not load-bearing for period detection; the model arrays are still on the TLS object if needed. Recorded here. |
| Workflow Considerations (preprocessing order, etc.)   | Mapped → `verify-preprocessing` step + `integrations`                    |
| Typical Parameter Ranges                              | Mapped → `assess-candidate` + `refine-period` step descriptions          |
| Multiple Planet Search Strategy                       | Mapped → `mask-and-search-next` step + scenario                          |
| When to Use TLS vs Lomb-Scargle                       | Mapped → `do_not_use_when` + `integrations`                              |
| Common Issues (flux_err required, 2x/0.5x aliasing, low SDE) | Mapped → `anti_patterns`                                          |
| References (TLS GitHub, lightkurve tutorials)         | Deliberately dropped — URLs trivially recoverable; body kept lean.       |

## Cross-skill notes

This skill is one of five under the parent task. It composes with:
- `light-curve-preprocessing` (quality cut, sigma-clip, flatten — runs *before*)
- `lomb-scargle-periodogram` (first-pass period search; flatten removes the
  rotation period it surfaces, then TLS finds the planet)
- `box-least-squares` (older, less-sensitive alternative to TLS)
- `exoplanet-workflows` (umbrella playbook orchestrating the end-to-end pipeline)
