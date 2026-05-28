# tess-exoplanet-period — source notes

## Intent

Author an AIP procedure skill that lets a downstream agent recover the
orbital period of a transiting exoplanet from a TESS-style light curve
where stellar activity dominates the raw flux variations. The agent's
sole input is the task instruction at
`vendor/skillsbench/tasks/exoplanet-detection-period/instruction.md`.

## Source material

The skill body is synthesised from a single source: the task instruction
file, which specifies:

- Input path: `/root/data/tess_lc.txt`
- Columns: time (MJD), normalized flux, quality flag (0 = good), flux
  uncertainty
- Pipeline: filter → detrend stellar activity → identify transit period
- Output: `/root/period.txt`, single number, 5 decimal places

No other in-repo skill, runbook, or worked example was consulted (this
"from instruction" authoring mode is the explicit constraint of the
benchmark).

Astronomy-domain choices in the skill body (BLS for transit search,
Savitzky-Golay for detrending stellar rotation, asymmetric sigma clip to
preserve transit dips, refinement on a fine grid) are standard transit
detection practice and represent the procedural knowledge an agent
would otherwise need to derive from scratch.

## Schema choice

Reused the canonical `procedure.schema.json` from the AIP skill's bundled
schemas (`assets/aip-schemas/procedure.schema.json`). The task is a
linear-with-branches procedure with decision rules and anti-patterns — a
textbook fit for the Procedure schema. No new schema needed.

## Resources bundled

- `scripts/detect_period.py` — end-to-end CLI: load → quality-filter →
  Savitzky-Golay detrend → asymmetric sigma-clip → BLS autopower →
  fine-grid refinement → write rounded period.
- `references/detrending.md` — loaded on demand if the default detrend
  fails (transit gets smoothed away or stellar variability leaks
  through); covers transit-masking iteration and biweight alternatives.

## Mapping check (source → body)

| Source content                                     | Where in body                                |
|----------------------------------------------------|----------------------------------------------|
| Input path and column layout                       | `steps.read-task-paths`, `steps.load-lightcurve` |
| Quality flag == 0 is "good"                        | `steps.quality-filter`                       |
| Filter outliers                                    | `steps.sigma-clip-outliers`                  |
| Remove stellar-activity variability                | `steps.detrend-stellar-activity`             |
| Identify exoplanet orbit period                    | `steps.bls-periodogram`, `steps.refine-peak` |
| Output path and 5-decimal rounding                 | `steps.write-output`                         |
| Example "2.44535" format                           | `steps.write-output` + `scenarios[0].outcome` |

Every distinct piece of the instruction is mapped. No deliberate drops.
