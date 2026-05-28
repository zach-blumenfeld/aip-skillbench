---
name: video-processor
description: Process videos by removing segments and concatenating remaining parts. Use when you need to remove detected pauses/openings from videos, create highlight reels, or batch process segment removals using ffmpeg filter_complex.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires ffmpeg (with libx264 + aac) and Python 3.11+.
---

```yaml
purpose: >
  Remove specified time segments from a video and concatenate the
  remaining parts into a single output using ffmpeg's filter_complex.
  Given one or more JSON files listing segments to remove (e.g.
  detected openings and pauses), it computes the complementary
  keep-segments as their inverse, builds the trim/concat filter graph,
  re-encodes with CRF (libx264 + aac) to preserve quality and audio
  sync, and writes a statistics report. Handles many removal segments
  in a single pass and the edge cases at the start and end of the
  video. Scope is the cut-and-concatenate step: segment *detection* is
  done upstream and supplied as input.

trigger_when:
  - Removing detected pauses/openings from a video and concatenating what remains.
  - Creating a highlight reel by keeping only specific spans of a recording.
  - Batch-processing many segment removals from one or more segments JSON files.
  - You already have the segments-to-remove (start/end/duration) and need a frame-accurate cut-and-concat with re-encode.

do_not_use_when:
  - You still need to *detect* the silence, pauses, or opening — produce the removal-segments JSON first (audio energy analysis, scene detection, etc.), then use this skill.
  - Sample-accurate cuts are required — this re-encodes and cuts are frame-accurate, not sample-accurate.

scope_and_approval: >
  Writes the output video and a sibling `<output>_report.json`,
  overwriting any existing file at the output path (ffmpeg runs with
  `-y`). Read-only on the input. Re-encoding is CPU-bound: budget
  roughly 0.3x the video duration (~20 min for a 65-min video) and
  ensure free disk for an output of ~70-80% of the input size. Faster
  on machines with 2+ CPU cores. No network access.

steps:
  - name: prepare-removal-segments
    description: >
      Collect the segment(s) to remove into one or more JSON files in
      the expected format. Each segment needs `start` and `end`
      seconds; include `duration` so the removal total can be summed.
      Accepted shapes: an object with a `segments` array, a bare
      array of segments, or a single segment object. Multiple files
      are merged and sorted by `start`. Detecting these segments is
      upstream of this skill.
    outputs:
      - name: removal-segments-files
        type: list[string]
        description: Path(s) to JSON file(s) listing segments to remove.
  - name: process-video
    description: >
      Run the processor. It (1) loads and sorts the removal segments,
      (2) probes the input duration with ffprobe, (3) computes the
      keep-segments as the inverse of the removals over [0, duration]
      — including the trailing tail — (4) builds a filter_complex that
      trim/atrim + setpts/asetpts each keep-segment and concats the
      video and audio streams, and (5) re-encodes (libx264 -preset
      medium -crf 23, aac 128k) and writes the stats report. Cuts are
      frame-accurate and audio stays in sync.
    script: scripts/process_video.py
    inputs:
      - name: input-video
        type: string
        description: Path to the input video file (--input).
      - name: output-video
        type: string
        description: Path to write the processed video (--output).
      - name: removal-segments-files
        type: list[string]
        description: One or more removal-segment JSON files (--remove-segments).
    outputs:
      - name: output-video
        type: string
        description: The concatenated, re-encoded video at the output path.
      - name: stats-report
        type: object
        description: Written to `<output>_report.json`; fields described in search_shortcuts.
  - name: verify-output
    description: >
      Confirm the output file exists and sanity-check the stats
      report: original_duration ≈ output_duration + removed_duration,
      compression_percentage is plausible, and the
      segments_removed / segments_kept counts match expectations. The
      report's output_duration is measured by ffprobe on the result,
      so it validates the actual cut rather than the planned one.
    depends_on:
      - process-video
    inputs:
      - name: stats-report
        type: object
      - name: output-video
        type: string

search_shortcuts:
  - category: CLI invocation
    body: |
      python3 scripts/process_video.py \
        --input /path/to/input.mp4 \
        --output /path/to/output.mp4 \
        --remove-segments /path/to/segments.json
      When mounted as a skill the absolute form is
      python3 /root/.claude/skills/video-processor/scripts/process_video.py ...
      --remove-segments accepts multiple files: --remove-segments opening.json pauses.json
  - category: Parameters
    body: |
      --input            Path to the input video file (required).
      --output           Path to the output video file (required).
      --remove-segments  One or more JSON files listing segments to remove (required, nargs+).
  - category: Removal-segment input format
    body: |
      Preferred: {"segments": [{"start": 0, "end": 600, "duration": 600},
                                {"start": 610, "end": 613, "duration": 3}]}
      Also accepted: a bare list of segment objects, or a single segment object.
      Multiple files are concatenated and sorted by start time before processing.
      start/end are seconds; duration is summed for the removal total in the report.
  - category: Stats report format (<output>_report.json)
    body: |
      original_duration       — input duration in seconds (ffprobe).
      output_duration         — measured output duration in seconds (ffprobe).
      removed_duration        — original_duration - output_duration.
      compression_percentage  — removed / original * 100, rounded to 2 dp.
      segments_removed        — count of removal segments loaded.
      segments_kept           — count of keep-segments concatenated.
      Note: this is the processor's internal stats report. It is keyed differently
      from any final task report that downstream tooling may require.
  - category: FFmpeg filter_complex example (3 keep-segments)
    body: |
      [0:v]trim=start=600:end=610,setpts=PTS-STARTPTS[v0];
      [0:a]atrim=start=600:end=610,asetpts=PTS-STARTPTS[a0];
      [0:v]trim=start=613:end=1000,setpts=PTS-STARTPTS[v1];
      [0:a]atrim=start=613:end=1000,asetpts=PTS-STARTPTS[a1];
      [v0][v1]concat=n=2:v=1:a=0[outv];
      [a0][a1]concat=n=2:v=0:a=1[outa]
  - category: Encoding settings (preserve quality)
    body: |
      -c:v libx264 -preset medium -crf 23  — balanced speed/quality, good size.
      -c:a aac -b:a 128k                    — re-encoded audio, kept in sync.
      Output runs with -y (overwrites). Output size ≈ 70-80% of input.
  - category: Dependencies
    body: |
      ffmpeg with libx264 and aac support; ffprobe (ships with ffmpeg).
      Python 3.11+. No third-party Python packages required.

scenarios:
  - need: Remove a detected opening and the long pauses from a 65-minute lecture.
    context: >
      Upstream detection produced opening.json and pauses.json listing
      the segments to remove (start/end/duration each).
    action: >
      python3 scripts/process_video.py --input /root/lecture.mp4
      --output /root/compressed.mp4 --remove-segments /root/opening.json
      /root/pauses.json
    outcome: >
      65 min → 51 min (≈21.2% compression); compressed.mp4 plus
      compressed_report.json with original/output/removed durations and
      segment counts.
  - need: Apply a single segments file with many cuts in one pass.
    action: >
      python3 scripts/process_video.py --input video.mp4 --output
      output.mp4 --remove-segments segments.json — the processor inverts
      the ~91 removal segments into the keep-segments and concatenates
      them in a single ffmpeg filter_complex.
    outcome: >
      One re-encoded output.mp4 with all removals applied and a report
      summarizing the compression.

anti_patterns:
  - Using this skill to find the silence/opening — it only cuts and concatenates segments supplied to it; detect first, then process.
  - Expecting sample-accurate cuts — the re-encode is frame-accurate; cut boundaries land on frame edges.
  - Omitting `duration` from removal segments — the removal-total sum relies on it (output_duration is still measured independently by ffprobe).
  - Running without enough free disk for an output ~70-80% of the input size, or assuming it is instant — budget ~0.3x the video duration to encode.
  - Pointing --output at a file you want to keep — ffmpeg runs with -y and overwrites it.
```
