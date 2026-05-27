---
name: report-generator
description: Generate compression reports for video processing. Use when you need to create structured JSON reports with duration statistics, compression ratios, and segment details after video processing.
compatibility: Requires Python 3.11+ and ffprobe (from ffmpeg) on PATH.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Generate a structured JSON compression report for a video-processing run.
  Measures the original and compressed durations with ffprobe, derives the
  removed duration and compression percentage, and merges in the list of
  removed segments when a segments JSON is provided.

trigger_when:
  - A video has been compressed and the caller needs a machine-readable summary of how much was removed.
  - Producing documentation or downstream metrics for a silence-removal or trim pipeline.
  - The user asks for a compression ratio, removed-duration total, or per-segment removal report.

do_not_use_when:
  - The original or compressed file is not on local disk (ffprobe runs locally).
  - The desired output is a human-readable narrative rather than structured JSON.

steps:
  - name: locate-inputs
    description: >
      Confirm the original video, the compressed video, and (optionally) the
      segments JSON exist on disk. The segments JSON, when provided, must
      contain a top-level `segments` array.
  - name: invoke-generator
    description: >
      Run `scripts/generate_report.py` with `--original`, `--compressed`,
      `--output`, and optionally `--segments`. The script calls ffprobe on
      both videos, computes `removed_duration = original - compressed` and
      `compression_percentage = (removed / original) * 100`, then writes the
      report JSON to the `--output` path.
  - name: verify-output
    description: >
      Open the output JSON and confirm it contains
      `original_duration_seconds`, `compressed_duration_seconds`,
      `removed_duration_seconds`, `compression_percentage`, and
      `segments_removed`. Durations are rounded to two decimal places.

decisions:
  - signal: No segments JSON is available (the upstream step did not record per-segment data).
    action: Omit `--segments`; the report's `segments_removed` field will be an empty list. The duration and percentage fields still populate correctly.
  - signal: ffprobe is missing or not on PATH.
    action: Install ffmpeg (which provides ffprobe) before running the script. The script will raise an error on `subprocess.run` otherwise.
  - signal: Compressed file is larger than the original (negative removed duration).
    action: Stop and investigate the upstream compression step. The report would show a negative `compression_percentage`, which is almost always a pipeline bug rather than a valid result.

scenarios:
  - need: Produce a compression report for a silence-removal pass over `data/input_video.mp4`.
    action: >
      python3 scripts/generate_report.py
      --original data/input_video.mp4
      --compressed compressed_video.mp4
      --segments all_segments.json
      --output compression_report.json
    outcome: |
      compression_report.json contains, for example:
      {
        "original_duration_seconds": 600.00,
        "compressed_duration_seconds": 351.00,
        "removed_duration_seconds": 249.00,
        "compression_percentage": 41.5,
        "segments_removed": [
          {"start": 0, "end": 221, "duration": 221, "type": "opening"},
          {"start": 610, "end": 613, "duration": 3, "type": "pause"}
        ]
      }

anti_patterns:
  - Computing durations by parsing filenames or trusting upstream metadata; always use ffprobe for accurate measurement.
  - Reporting compression as `compressed / original` instead of `removed / original * 100`.
  - Passing a segments JSON whose top-level shape is a bare array; the script expects an object with a `segments` key.
```
