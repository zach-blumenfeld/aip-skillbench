# segment-combiner — AIP conversion notes

Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/video-silence-remover/environment/skills/segment-combiner/`
into AIP format.

## Schema choice

Reused the bundled [`procedure.schema.json`](procedure.schema.json) from the
AIP skill (`procedure` schema). The original skill is a small, linear
"combine segment JSON files" procedure with a clear trigger, one
invocation command, and notes about input/output formats — a good fit for
the procedure schema (`purpose`, `trigger_when`, `steps`, plus optional
`scenarios` and `anti_patterns`).

## Mapping

- Title + description → `purpose` + frontmatter `description`.
- "Use Cases" → `trigger_when` list.
- "Usage" command + parameters → `steps` (invoke script with required
  args) and the worked invocation lives in `scenarios`.
- "Input Format" / "Output Format" → captured inside the relevant step
  descriptions so the agent knows the JSON shape the script accepts and
  emits without loading external references.
- "Dependencies" (Python 3.11+) → frontmatter `compatibility`.
- "Notes" — "Segments are sorted by start time", "Compatible with
  video-processor --remove-segments input", "All input files must have
  `segments` array" → `anti_patterns` (the must-have) and
  `decisions`/notes embedded in the appropriate step.

## Deliberate drops

None — every distinct piece of source content is captured either in the
body, frontmatter, or step descriptions.

## Name

Preserved as `segment-combiner` — required by the task harness so the
mounted skill path resolves.
