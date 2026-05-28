# segment-combiner — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `segment-combiner` (the
`aip-from-curated` track for the `video-silence-remover` task). The canonical
original is preserved verbatim at `source/ORIGINAL_SKILL.md`; the curated tool
is copied verbatim to `scripts/combine_segments.py`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/combine_segments.py` — verbatim copy of the curated combiner
  (reads each input's `segments` array, concatenates {start, end, duration}
  entries, sorts by start, sums durations, writes
  {segments, total_segments, total_duration_seconds}).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the
  body validates against. Bundled locally so the skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a tiny
execution graph: gather the segment files → run one combiner script that
produces the unified output. That is exactly what the procedure schema models
(script-backed step nodes connected by inputs/outputs).

## Non-obvious behavior surfaced from the script

Reading `scripts/combine_segments.py` reveals behavior the prose original only
implies. These are captured in the body so an agent does not learn them by
trial and error:

- **Concatenate-and-sort only, no merge/dedupe.** Overlapping or adjacent
  segments from different detectors are kept as separate entries. Surfaced in
  `purpose`, `do_not_use_when`, and `anti_patterns`.
- **Missing `segments` array is silently skipped.** The `if "segments" in
  data` guard means a malformed input contributes nothing and raises no error.
  Surfaced in the `gather-segment-files` description and `anti_patterns`.
- **Each segment needs `start`, `end`, AND `duration`.** The script reads all
  three keys directly (`seg["duration"]` etc.), so a missing key raises
  KeyError. Surfaced in the same step description and `anti_patterns`.

## Source-content classification (completeness check)

- Title + "Combines multiple segment JSON files into a single unified
  segments file" → **Mapped** to `purpose`.
- "Use Cases" (merge from multiple detectors / consolidate results / prepare
  unified input for video-processor) → **Mapped** to `trigger_when`.
- "Usage" + "Parameters" (`--segments` one-or-more files, `--output` path) →
  **Mapped** to the `combine-segments` step (script-backed) and its inputs.
- "Input Format" (each file has a `segments` array of {start, end, duration})
  → **Mapped** to the `gather-segment-files` step description.
- "Output Format" ({segments, total_segments, total_duration_seconds}) →
  **Mapped** to the `combine-segments` output `combined-segments`.
- "Dependencies: Python 3.11+" → **Mapped** to `compatibility` frontmatter.
- "Example" (combine initial_silence.json + pauses.json) → **Mapped** to a
  `scenario`.
- "Notes" — sorted by start time → **Mapped** to `purpose` + the
  `combine-segments` description. Compatible with video-processor
  --remove-segments → **Mapped** to `trigger_when` + a `scenario`. All input
  files must have `segments` array → **Mapped** to the `gather-segment-files`
  description + an `anti_pattern`.
- Hard-coded example path `/root/.claude/skills/segment-combiner/scripts` →
  **Deliberate drop** of the literal mount path. The body references the
  script by its in-skill relative path (`scripts/combine_segments.py`) so the
  skill is portable; the absolute mount path is environment-specific.

## Single combiner step is intentionally script-backed, gathering is prose

The combine step is a pure script invocation, so it is a `script:` node — the
right call per AIP best practice (it does numeric work: sort + sum). The
preceding `gather-segment-files` step stays prose because its "logic" is just
the agent selecting which files to merge and where to write — there is no
fixed rule or table to encode, and the inputs (which detector files exist)
are task-specific and unknown at authoring time.
