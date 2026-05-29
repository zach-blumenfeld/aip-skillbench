# Source materials and authoring notes

This AIP skill was compiled from a single source: the curated Agent
Skill `unit-commitment-data-modeling/SKILL.md` shipped with the
SkillsBench `energy-unit-commitment` task. The original is bundled
here verbatim as `ORIGINAL_SKILL.md` so the transformation is auditable.

## Schema choice

- **Schema:** `procedure.schema.json` (bundled in this folder).
- **Why:** The source skill is a parsing workflow — a directed sequence
  of steps with intermediate artifacts (raw data → schema survey →
  field mapping → normalized case dict → validation report). That fits
  the procedure schema's "graph of script-backed nodes connected by
  inputs and outputs" model. No new schema was authored.

## Script vs prose decisions

Following the AIP guidance to *script the deterministic/mechanical
parts and leave data-dependent interpretive logic as prose*:

| Step                       | Form   | Why                                                                                          |
| -------------------------- | ------ | -------------------------------------------------------------------------------------------- |
| load-data                  | prose  | Source format varies (JSON/CSV/sheet/DB); the agent picks the right parser.                  |
| inspect-schema             | prose  | Pure interpretation of unknown structure.                                                    |
| identify-time-axis         | prose  | The "time axis" can be a count, a list of timestamps, or implied by series length.           |
| identify-resource-sets     | prose  | Categorization by role; benchmark-dependent naming.                                          |
| map-fields-to-concepts     | prose  | Meaning/units/shape mapping is judgment, not lookup. Concept table is reference data.        |
| check-units-and-conventions| prose  | Reading and reconciling source-declared units is interpretive.                               |
| normalize-into-case-dict   | prose  | Constructive step shaped by upstream decisions.                                              |
| parse-startup-tiers        | script | `choose_startup_tier` — deterministic sort + threshold pick over `{lag, cost}` records.      |
| parse-cost-curves          | script | `interpolate_total_cost` — deterministic piecewise-linear interpolation.                     |
| handle-renewables          | prose  | Min/max parsing is mechanical but the curtailment vs fixed decision depends on the task.     |
| validate-parsed-case       | script | Fixed set of structural and finiteness checks over the normalized dict.                      |

Production-convention conversion (output-above-minimum ↔ actual MW) is
two trivial formulas. They're exposed as helpers in `uc_data_helpers.py`
(`actual_from_above_min`, `above_min_from_actual`) so callers don't
re-derive them, but no step is dedicated solely to running them — the
convention is recorded in `conventions` and applied where the modeling
code needs it.

## Bundled scripts

- `scripts/uc_data_helpers.py` — pure library: `choose_startup_tier`,
  `interpolate_total_cost`, `actual_from_above_min`,
  `above_min_from_actual`. Importable from any parsing/modeling code.
- `scripts/validate_parsed_case.py` — CLI + library
  (`validate_case(case)`) that runs every parser-level check from the
  source's "Parser-Level Validation" + "Common Mistakes" sections.

The helpers were consolidated into a single module (rather than one
file per function) because they share no state, are short, and are
typically imported together. The validator is its own script because
it is callable as a CLI and represents a distinct gate.

## Source content classification

Every distinct piece of the original `ORIGINAL_SKILL.md` is accounted
for in the compiled body:

- **Mapped (verbatim or reworded into a step):** parsing workflow,
  concept-to-name mapping table, common data shapes, time/order/units
  rules, production convention, startup-tier code, cost-curve code,
  renewables rules, parser-level validation, common mistakes.
- **Schema gap:** none.
- **Body drop:** none.
- **Deliberate drop:** none — content density is similar to the source.

The two embedded Python snippets in the source (`choose_startup_tier`
and `interpolate_total_cost`) are moved into `scripts/uc_data_helpers.py`
and referenced from the relevant steps via the schema's `script:` field,
not inlined as prose — that's the script-first guidance applied.
