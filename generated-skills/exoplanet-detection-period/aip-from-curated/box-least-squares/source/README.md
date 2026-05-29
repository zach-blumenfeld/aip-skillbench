# Source notes — box-least-squares (AIP from curated)

## Origin
Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills/box-least-squares/SKILL.md`
into AIP format. Original copied verbatim to `source/SKILL.md` for traceability.

## Schema choice
`procedure.schema.json` (existing AIP schema, reused).

Why: the curated SKILL.md is a step-by-step recipe — prepare data, choose a
period/duration grid, run BLS, inspect peak statistics, validate against
SNR / odd-even / transit-count thresholds, phase-fold for confirmation.
That is the canonical shape `procedure` was designed for; no new schema needed.

## Script choice
One script, `scripts/run_bls.py`. Backs the `compute-bls` step.

- **Deterministic and tabular** — wraps `astropy.timeseries.BoxLeastSquares`,
  calls `autopower(durations)`, then `compute_stats()` on the strongest peak.
  Emits JSON with the strongest period plus the top-N peaks and the validation
  statistics (depth, depth_err, depth_snr, depth_odd, depth_even, transit_count).
  The agent reads this back and reasons about whether the candidate is real.
- **Why not script `interpret-candidate`** — the SNR > 7 / odd-even-mismatch /
  enough-transits judgement is a domain decision that depends on what else the
  agent knows about the target (eclipsing-binary priors, instrument quirks,
  user intent). A script that emits the raw stats gives the agent the data it
  needs without prescribing an answer. The thresholds live as prose so the
  agent can reason around edge cases.
- **Why not script `select-search-config`** — the typical-range table is a
  lookup, but the agent must *judge* which science case applies from the
  user's prompt and the data context. Lookup table lives in `search_shortcuts`.
- **Why not script `phase-fold-visualize`** — plotting is an optional visual
  sanity check; not deterministic logic worth pinning.

## Script behaviour vs source

The source SKILL.md exposes two BLS objectives (`likelihood` default, `snr`).
`run_bls.py` defaults to `likelihood` and exposes `--objective` so the agent
can switch. `compute_stats()` is always run on the strongest peak so the
validation step has everything it needs in a single invocation.

The source also discusses `power()` with a custom period grid. The script
uses `autopower()` (and `autoperiod()` is reachable via the `--min-period`
and `--max-period` flags). `power()` with a hand-rolled grid is rare in
practice; if the agent needs it, drop into Python directly.

## Completeness mapping (source → body)

| Source content                                       | Disposition                                    |
|------------------------------------------------------|------------------------------------------------|
| "What BLS is" overview                                | Mapped → `purpose`                             |
| Installation / Dependencies                          | Mapped → frontmatter `compatibility`           |
| Basic Usage code snippet                              | Mapped → `compute-bls` step + script           |
| `autopower` vs `power` discussion                     | Mapped → `compute-bls` step + script flags     |
| Objective functions (likelihood, snr)                 | Mapped → `compute-bls` step + `--objective` flag |
| Complete Example (multiple durations, plotting)       | Mapped → `compute-bls` step + scenarios        |
| `compute_stats()` validation                          | Mapped → `compute-bls` script (always run) + `interpret-candidate` |
| Validation criteria (SNR>7, odd-even, transits)       | Mapped → `interpret-candidate` step + anti-patterns |
| Period grid sensitivity / `autoperiod`                | Mapped → `select-search-config` step prose     |
| Top-N peaks comparison                                | Mapped → `compute-bls` script `--top` output   |
| Phase-folded light curve                              | Mapped → `phase-fold-visualize` step           |
| BLS vs TLS comparison                                 | Mapped → `do_not_use_when` + `integrations`    |
| Integration with preprocessing                        | Mapped → `integrations` (light-curve-preprocessing) |
| Common Issues (no peak, 2× / 0.5× period, odd-even)   | Mapped → `anti_patterns` + `scenarios`         |
| References (URLs, papers)                             | Mapped → `search_shortcuts` (compact)          |
| "When to use BLS" decision matrix                     | Mapped → `do_not_use_when` + `integrations`    |

## Cross-skill notes
This skill is one of five under the parent task. It composes with:
- `light-curve-preprocessing` (filter, sigma-clip, flatten — runs *before* this)
- `transit-least-squares` (more sensitive than BLS; often run alongside as a cross-check)
- `lomb-scargle-periodogram` (general periodic signal search, runs before transit-specific tools)
- `exoplanet-workflows` (the umbrella playbook for end-to-end exoplanet period detection)
