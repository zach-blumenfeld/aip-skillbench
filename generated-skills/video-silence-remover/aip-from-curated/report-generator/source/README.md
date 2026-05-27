# Source Notes — report-generator (AIP)

This AIP skill is a 1:1 conversion of the curated Agent Skill at
`vendor/skillsbench/tasks/video-silence-remover/environment/skills/report-generator/`.

## Schema choice

`procedure.schema.json` (bundled in this folder). The source skill is a
single CLI invocation with parameters, output format, and notes — a
short execution procedure. The procedure schema covers
`purpose`, `trigger_when`, `steps`, `decisions`, `scenarios`, and
`anti_patterns`, which is sufficient to encode every section of the
source `SKILL.md`. No new schema was needed.

## Mapping (source SKILL.md → AIP body)

- Top description + "Use Cases" → `purpose` + `trigger_when`.
- "Usage" + "Parameters" → `steps` (invoke + required flags).
- "Output Format" → `scenarios` (worked example with the JSON shape).
- "Dependencies" → `compatibility` frontmatter field.
- "Notes" (ffprobe accuracy, compression formula) → `anti_patterns`
  and inline step description.
- "Example" → `scenarios`.

## Deliberate drops

- The hardcoded install path `/root/.claude/skills/report-generator/scripts/generate_report.py`
  in the source `SKILL.md` is preserved in the body so the curated task
  environment (which mounts the skill at that path) still works. The
  AIP body references `scripts/generate_report.py` relatively as well.

## Constraints honored

- `name: report-generator` is unchanged — the task harness mounts the
  skill under that exact name.
- Every non-`SKILL.md` file from the source skill is copied verbatim.
