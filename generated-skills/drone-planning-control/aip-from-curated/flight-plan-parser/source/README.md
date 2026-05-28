# Source README — flight-plan-parser (AIP conversion)

This folder bundles the canonical sources used to compile the AIP
`SKILL.md` for `flight-plan-parser`.

## Files

- `procedure.schema.json` — the AIP procedure schema this skill validates
  against. Bundled locally so the skill is self-contained.
- `ORIGINAL_SKILL.md` — verbatim copy of the curated Agent Skill
  `SKILL.md` from
  `vendor/skillsbench/tasks/drone-planning-control/environment/skills/flight-plan-parser/SKILL.md`.

## Conversion notes

- Schema choice: `procedure` — the source describes a multi-step parsing
  procedure (parse commands → maintain state → emit waypoints/times/modes).
- The original source contained no `scripts/`, `references/`, or `assets/`
  subdirectories, so none were carried over.
- Frontmatter `name` is preserved as `flight-plan-parser` per the task
  contract (the task's mounted skill name must match).

## Source-to-body mapping

- **Overview** → `purpose`.
- **Output Format** → `purpose` (output contract paragraph).
- **Supported Commands** table → `search_shortcuts` entry (`commands`
  category) so the four command patterns remain queryable as a group.
- **Implementation Logic** → ordered `steps` (init-parser →
  auto-insert-start → parse-line → finalize-arrays → expose-entrypoint).
- **Regex Strategy** → step `parse-line` description and a dedicated
  `regex` search-shortcut entry covering capture groups and flags.
- **Key Design Rules** → `decisions` (signal → action) for the
  start-waypoint and copy-position invariants.
- **Usage** example → `scenarios` entry.
- No content was deliberately dropped.
