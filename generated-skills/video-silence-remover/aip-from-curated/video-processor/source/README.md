# Source materials — video-processor (AIP compilation)

This skill was compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/video-silence-remover/environment/skills/video-processor/`
into AIP format. The original SKILL.md is preserved verbatim in
`ORIGINAL_SKILL.md`, and the schema the AIP body validates against is bundled as
`procedure.schema.json` (the canonical `procedure` schema from the AIP spec —
`$id: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`).

The `name:` frontmatter is unchanged (`video-processor`) so the mounted skill
name matches what the task expects.

## Role in the task

The `video-silence-remover` task ships a pipeline of composable skills
(audio-extractor → energy-calculator → silence-detector → pause-detector →
segment-combiner → **video-processor** → report-generator). This skill is the
**cut-and-concatenate** node: it takes the already-detected removal segments as
input and produces the trimmed, re-encoded video. Detection of the opening and
pauses, and generation of the task's final `compression_report.json`, are the
jobs of sibling skills. The conversion preserves that scope rather than
expanding video-processor to cover detection — faithfulness to the curated skill
is what makes the aip-from-curated variant a valid A/B comparison.

## Schema choice

The original is a single-script processing pipeline: load removal segments →
invert to keep-segments → build an ffmpeg filter_complex → re-encode → write a
stats report. That is exactly the execution graph the `procedure` schema models
(`steps` with `inputs`/`outputs` edges and a `script:`-backed node), and the
schema's optional fields (`scope_and_approval`, `search_shortcuts`, `scenarios`,
`anti_patterns`, `do_not_use_when`) carry the remaining reference content. So
`procedure` was adopted as-is rather than drafting a new schema — consistent with
the other conversions in this repo and with AIP's bias toward schema reuse.

## Single-script node modeling

`scripts/process_video.py` performs all five "How It Works" stages internally in
one invocation. Representing those five stages as five separate `script:`-backed
steps would falsely imply five invocations of the same script. Instead the body
models the real agent-facing graph:

- `prepare-removal-segments` — agent assembles the removal-segments JSON (no
  script; the input comes from upstream detection).
- `process-video` — the one script-backed node; its description enumerates the
  five internal stages (load/sort, ffprobe duration, invert to keep-segments,
  build filter_complex, re-encode + report) so none of that knowledge is lost.
- `verify-output` — agent sanity-checks the emitted stats report.

The keep-segment inversion algorithm and the filter_complex construction live in
the script (the source of truth); the filter_complex *shape* is also reproduced
verbatim in `search_shortcuts` as a reference, exactly as the original SKILL.md
presented it.

## Content mapping (completeness check)

Every distinct piece of the original SKILL.md was classified — all **mapped**, no
drops:

- **Title + intro** ("processes videos by removing specified segments and
  concatenating … using filter_complex") → `purpose`.
- **Use Cases** (remove pauses/openings, highlight reels, batch removals) →
  `trigger_when`.
- **Usage / CLI command** → `search_shortcuts[CLI invocation]` (both the relative
  and the mounted `/root/.claude/skills/...` absolute forms).
- **Parameters** (`--input`, `--output`, `--remove-segments`) →
  `search_shortcuts[Parameters]` and the `process-video` step `inputs`.
- **Input Segment Format** (segments object / bare list / single object; multiple
  files merged + sorted) → `search_shortcuts[Removal-segment input format]` and
  the `prepare-removal-segments` step.
- **Output / report JSON** → `search_shortcuts[Stats report format]` (with a note
  that this internal stats report is keyed differently from any final task report
  produced downstream — see below) and the `process-video` `stats-report` output.
- **How It Works** (5 stages) → enumerated inside the `process-video` step
  description.
- **FFmpeg Filter Example** → `search_shortcuts[FFmpeg filter_complex example]`,
  reproduced verbatim.
- **Dependencies** (ffmpeg + libx264/aac, Python 3.11+) → `compatibility`
  frontmatter and `search_shortcuts[Dependencies]`.
- **Limitations** (≈0.3x processing time, disk ~70-80%, frame- not
  sample-accurate) → `scope_and_approval`, `do_not_use_when`, and `anti_patterns`.
- **Example** (opening + pause removal, 65 → 51 min, 21.2%) → `scenarios`.
- **Performance Tips** (`-preset medium`, `-crf 23`, 2+ cores) →
  `search_shortcuts[Encoding settings]` and `scope_and_approval`.
- **Notes** (CRF quality, audio sync, start/end edge cases, statistics) → folded
  into `purpose`, the `process-video` step, and `verify-output`.

## Report-format note (deliberate non-change)

`process_video.py` writes a report keyed `original_duration`, `output_duration`,
`removed_duration`, `compression_percentage`, `segments_removed` (an integer
count), `segments_kept`. The task's `instruction.md` asks for a final
`compression_report.json` keyed `original_duration_seconds`,
`compressed_duration_seconds`, `removed_duration_seconds`,
`compression_percentage`, and `segments_removed` (an array of objects). These do
not match — and that is correct: in the oracle pipeline the final report is
produced by the separate `report-generator` skill, not by video-processor. The
script is therefore copied **verbatim** (not altered to the task's format) to
stay faithful to the curated skill, and `search_shortcuts[Stats report format]`
documents the processor's actual keys with a note about the distinction.

## Scripts

`scripts/process_video.py` is copied byte-for-byte from the source skill; the AIP
body references it by the same relative path the original used.
