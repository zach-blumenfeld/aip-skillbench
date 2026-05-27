---
name: segment-combiner
description: Combine multiple segment detection results into a unified list. Use when you need to merge segments from different detectors, prepare removal lists for video processing, or consolidate detection outputs.
compatibility: Requires Python 3.11+
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Combine multiple segment JSON files (silence detections, pause detections,
  etc.) into a single unified segments file ready for downstream video
  processing. The combiner sorts segments by start time and reports total
  removal duration so the result is a drop-in input for video-processor
  --remove-segments.

trigger_when:
  - Merging segments produced by multiple detectors (e.g., initial-silence
    plus pause detection).
  - Consolidating detection results from separate runs into one file.
  - Preparing a unified `--remove-segments` input for video-processor.

steps:
  - name: gather-inputs
    description: >
      Collect every segment JSON file to merge. Each input must be a JSON
      object with a top-level `segments` array; each segment is
      `{start, end, duration}` in seconds. Skill fails on inputs that lack
      `segments`.
  - name: run-combiner
    description: >
      Invoke the combiner script with one or more `--segments` paths and an
      `--output` path. Example:
      `python3 scripts/combine_segments.py --segments initial_silence.json pauses.json --output all_segments.json`.
      The script concatenates segments across files, sorts by `start`, sums
      `duration`, and writes a JSON object
      `{segments, total_segments, total_duration_seconds}`.
    depends_on: [gather-inputs]
  - name: hand-off
    description: >
      Pass the resulting `all_segments.json` to video-processor via
      `--remove-segments all_segments.json`. The output schema matches what
      video-processor expects, so no further transformation is needed.
    depends_on: [run-combiner]

scenarios:
  - need: >
      Two detectors produced `initial_silence.json` and `pauses.json`; the
      video pipeline needs a single removal list.
    action: >
      Run
      `python3 /root/.claude/skills/segment-combiner/scripts/combine_segments.py
      --segments initial_silence.json pauses.json
      --output all_segments.json`.
    outcome: >
      `all_segments.json` contains every segment, sorted by start time, with
      `total_segments` and `total_duration_seconds` populated — ready for
      video-processor.

anti_patterns:
  - Passing input files that lack a top-level `segments` array — the script
    will silently skip them. Verify each input is a JSON object with a
    `segments` array of `start` / `end` / `duration` records first.
  - Re-sorting or de-duplicating the combined output by hand — the script
    already sorts by start time; downstream tools rely on that ordering.
  - Transforming the output before passing it to video-processor — the
    emitted schema is already what `--remove-segments` expects.
```
