# video-processor — AIP conversion notes

Converted from the curated SkillsBench skill at
`vendor/skillsbench/tasks/video-silence-remover/environment/skills/video-processor`
into AIP format.

## Schema choice

The original SKILL.md is a procedural runbook for invoking
`scripts/process_video.py` with the right inputs, understanding its
output report, and respecting its limitations. That maps cleanly onto
[`procedure.schema.json`](procedure.schema.json) — it has the right
fields for `purpose`, `trigger_when`, `steps`, `decisions`,
`anti_patterns`, and `scenarios`. No new schema was needed.

## Name preservation

`name: video-processor` is preserved verbatim — the SkillsBench task
mounts the skill at `/root/.claude/skills/video-processor/` and the
folder name must match.

## Content mapping (source → AIP body)

- "Use Cases" → `trigger_when`.
- "Usage", "Parameters", "Input Segment Format", "Example" → `steps`
  and `scenarios`. The exact CLI invocation is preserved in the
  `invoke-processor` step so the agent has the literal command.
- "Output" report shape → preserved in the `verify-output` step as a
  YAML block scalar.
- "How It Works" → `steps` (the script encapsulates the actual work;
  steps describe what the agent orchestrates around the script).
- "FFmpeg Filter Example" → kept as a scenario `context` so an agent
  debugging the filter has the literal template at hand.
- "Dependencies" → `compatibility` frontmatter.
- "Limitations", "Performance Tips", "Notes" → `decisions` and
  `anti_patterns` where the content is actionable; otherwise rolled
  into step descriptions.

## Deliberate drops

None — all source content is mapped into the AIP body or frontmatter.
