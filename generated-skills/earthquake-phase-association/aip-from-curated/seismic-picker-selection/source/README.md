# Source materials for `seismic-picker-selection`

This directory bundles the canonical inputs to the AIP conversion of this skill.

## Contents

- `procedure.schema.json` — AIP `Procedure` schema this skill validates against (`metadata.aip.schemaId` in `SKILL.md` matches this file's `$id`).
- `ORIGINAL-SKILL.md` — the source SKILL.md from `vendor/skillsbench/tasks/earthquake-phase-association/environment/skills/seismic-picker-selection/SKILL.md`, retained verbatim as the human-readable source.

## Conversion logic & intent

The source skill is a *method-selection guide* — it lays out tradeoffs across four earthquake event detection / phase picking methods (STA/LTA, Template Matching, Deep Learning, Manual) so an agent can pick the right one for the task at hand.

The `procedure` schema is the right fit: the agent's work here is a short decision procedure (assess context → review tradeoffs → select method), with per-method facts captured as `modes` (label + freeform body) and the signal→method routing captured in `decisions`. Per-method advantages/limitations would lose structure if flattened into typed sub-fields, so they stay in `modes[].body` prose to preserve the original's nuance.

### Field mapping

| Source content | AIP location |
| --- | --- |
| Skill premise + workshop attribution | `purpose` |
| When to reach for the skill | `trigger_when` |
| Tradeoff axes & per-method overview table | `steps[review-tradeoffs]` + `modes[].body` (each method ends with the table row's four-axis summary) |
| STA/LTA advantages & limitations | `modes[STA/LTA].body` |
| Template Matching advantages & limitations | `modes[Template Matching].body` |
| Deep Learning when-to-use + advantages + limitations | `modes[Deep Learning].body` |
| Manual (table row only) | `modes[Manual].body` |
| "Use STA/LTA when X, deep-learning when Y" routing | `decisions` |
| Common ways an agent could pick wrong | `anti_patterns` |
| Academic references | `purpose` (workshop citation) + tail of the body via a `references[]`-style mode is *not* used — kept inline in `purpose` since the schema has no citations field and creating a separate `references/` directory wasn't warranted for a short citation list |

### Deliberate drops

None. Every distinct piece of source content lands in the AIP body. The reference list is preserved in `purpose` rather than dropped.
