# Source notes — exoplanet-workflows AIP conversion

## Inputs

- `original-SKILL.md` — the curated freeform-markdown skill being converted.
- `procedure.schema.json` — AIP procedure schema (shared, bundled here so
  the skill is self-contained).

## Schema choice

Reused the shared `procedure.schema.json`. The original SKILL.md is an
orchestrator: a sequence of stages (load → quality control → preprocess →
period search → validate → refine) with deterministic thresholds. That maps
directly onto a procedure with script-backed steps.

## Script vs prose split

Pulled out into scripts (deterministic, would drift if re-prosed each run):

- `scripts/detect_period.py` — the canonical TLS recipe (quality flag
  filter, sigma=3 outlier removal, flatten, TLS broad search, refined ±5%
  search). Mirrors the task's `solve.sh` and the workflow's "pipeline design
  principles" section. Single script keeps the recipe atomic.
- `scripts/validate_candidate.py` — fixed thresholds (SDE 6/9, SNR 7,
  3σ odd-even mismatch) and aliasing warnings. Lookup-table / threshold
  logic — exactly what the AIP best-practices section says to script.
- `scripts/period_range_guide.py` — lookup table for period ranges per
  planet/star type and expected transit depths. Lookup tables are scripted.

Left as prose steps (judgment / data interpretation):

- Method selection (TLS vs Lomb-Scargle vs BLS). Hinges on the *kind* of
  signal you're after, which requires interpreting what the data looks
  like — not a deterministic rule.
- Inspecting plots / phase-folded light curves.
- Deciding to refine vs report (the agent reads the script's verdict and
  decides).

## References

Pushed two long blocks into `references/` so they only load when needed:

- `references/method-selection.md` — full when-to-use rationale per
  algorithm. Body keeps a one-liner; agent loads the file only if it needs
  to justify the choice.
- `references/troubleshooting.md` — the original SKILL.md's "Common Issues
  and Solutions" section. Body points the agent at it on validation failure.

## Source content classification

Every distinct piece of content from `original-SKILL.md` was mapped:

| Original section                          | Disposition       |
|-------------------------------------------|-------------------|
| Overview / pipeline stages                | body.purpose + steps |
| Pipeline design principles                | body.steps + anti_patterns |
| Critical decisions (preprocess / range)   | scripts + prose steps |
| Choosing the right method (TLS/LS/BLS)    | refs/method-selection.md |
| Signal validation (SDE, SNR, odd-even)    | scripts/validate_candidate.py |
| Multi-planet systems                      | refs/troubleshooting.md |
| Common issues and solutions               | refs/troubleshooting.md |
| Expected transit depths                   | scripts/period_range_guide.py (--depth-class) |
| Period range guidelines                   | scripts/period_range_guide.py |
| Best practices                            | body.anti_patterns (inverted where applicable) |
| References / Dependencies                 | body.search_shortcuts |

No source content was deliberately dropped.
