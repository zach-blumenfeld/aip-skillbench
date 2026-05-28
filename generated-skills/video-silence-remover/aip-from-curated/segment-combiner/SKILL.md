---
name: segment-combiner
description: "Combine multiple segment-detection JSON files into one unified, start-sorted segments list for video processing. Use when merging segments from different detectors, consolidating detection outputs, or preparing a removal list for video-processor --remove-segments."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+ (standard library only — argparse, json). No third-party packages.
---

```yaml
purpose: >
  Combine multiple segment-detection JSON files into a single unified,
  start-sorted segments list ready for video removal, using the bundled
  `scripts/combine_segments.py`. Each input file contributes the entries of
  its top-level `segments` array; the output adds `total_segments` and
  `total_duration_seconds`. The combiner concatenates and sorts by start time
  only — it does NOT merge or deduplicate overlapping or adjacent segments.

trigger_when:
  - Merging segment outputs from multiple detectors (e.g. an initial-silence detector plus a pause detector).
  - Consolidating several detection result files into one removal list.
  - Preparing a unified segments file as input to video-processor --remove-segments.
  - User mentions combining or merging segments, removal lists, or consolidating detection outputs.

do_not_use_when:
  - You need overlapping or adjacent segments merged/deduplicated — the combiner only concatenates and sorts.
  - You already have a single segments file in the correct format — no combination is needed.

scope_and_approval: >
  Read-only on the input files; writes only the single output JSON path you
  supply. No network access and no destructive operations. Safe to run
  without prompting.

steps:
  - name: gather-segment-files
    description: >
      Identify the two-or-more segment JSON files to merge and choose the
      output path. Each input must contain a top-level `segments` array whose
      items each carry `start`, `end`, and `duration` keys. A file lacking a
      `segments` array is silently skipped by the combiner; a segment missing
      `duration` (or `start`/`end`) raises a KeyError — verify the shape first.
    outputs:
      - name: segment-files
        type: list[string]
        description: Absolute paths of the input segment JSON files to combine (two or more).
      - name: output-path
        type: string
        description: Destination path for the combined segments JSON.
  - name: combine-segments
    description: >
      Run `combine_segments.py` with `--segments` (the input files, space
      separated) and `--output` (the destination). It extracts every
      {start, end, duration} from each file's `segments` array, sorts the
      merged list by `start`, sums the durations, and writes
      {segments, total_segments, total_duration_seconds}.
    script: scripts/combine_segments.py
    depends_on: [gather-segment-files]
    inputs:
      - name: segment-files
        type: list[string]
      - name: output-path
        type: string
    outputs:
      - name: combined-segments
        type: object
        description: >
          Written JSON — `segments` (sorted by start), `total_segments`
          (count), and `total_duration_seconds` (sum of all durations).

scenarios:
  - need: Two detectors produced initial_silence.json and pauses.json; one unified removal list is required.
    action: >
      Run `combine_segments.py --segments initial_silence.json pauses.json
      --output all_segments.json`.
    outcome: all_segments.json holds both detectors' segments sorted by start, with total_segments and total_duration_seconds.
  - need: The combined file must feed the downstream video remover.
    action: Pass the combined output as the segments input to video-processor --remove-segments.
    outcome: The processor removes every combined segment; the output shape is already compatible with --remove-segments.

anti_patterns:
  - Hand-merging segment JSON instead of running the script — you lose the start-sort and the recomputed totals, and downstream tools expect that exact shape.
  - Expecting overlapping or adjacent segments to be merged or deduplicated — the combiner concatenates and sorts only, so overlaps remain as separate entries.
  - Passing a file whose top-level `segments` array is missing — it is silently skipped, so its segments vanish from the output with no error.
  - Passing a segment missing `start`, `end`, or `duration` — the script reads each key directly and raises KeyError; ensure every segment carries all three.
```
