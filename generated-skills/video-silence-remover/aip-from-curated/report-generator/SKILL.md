---
name: report-generator
description: Generate compression reports for video processing. Use when you need to create structured JSON reports with duration statistics, compression ratios, and segment details after video processing.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+ and ffprobe (from ffmpeg) on PATH. Measures durations from real media files; reads a segments JSON it does not produce. No network access.
---

```yaml
purpose: >
  Produce the final compression report for a video-trimming pipeline. The
  bundled tool (`scripts/generate_report.py`) measures the original and
  compressed video durations with ffprobe, derives the removed duration
  (original − compressed) and compression percentage
  ((removed / original) × 100), copies the removed-segment list from a segments
  JSON, and writes a structured report JSON. All numeric logic lives in the
  script. The report's `segments_removed` is copied verbatim from the segments
  file's `segments` array — the script does not recompute, validate, or sum
  segment values, so the segments JSON must already accurately describe what was
  cut from the video.

trigger_when:
  - Documenting the results of a video silence/pause removal after the compressed video exists.
  - You need a structured JSON report with original/compressed/removed durations and a compression percentage.
  - Final step of a trim pipeline — summarizing what was removed alongside the produced video.
  - User asks for compression statistics or a "compression_report.json" describing the cut.

do_not_use_when:
  - The compressed video does not exist yet — produce it first (e.g. via video-processor); ffprobe must read a real, playable file.
  - You have not detected/combined the removed segments yet — this skill reports them, it does not find them. Run the detectors and segment-combiner first.
  - You only need to detect silence/pauses or cut the video — those are other skills; this one only reports.

scope_and_approval: >
  Reads two media files (original + compressed) via ffprobe and one segments
  JSON, then writes one report JSON to the path passed via `--output`. No
  network access, no media decoding or mutation, no in-place edits to inputs.
  Safe to run without prompting.

steps:
  - name: generate-report
    description: >
      Run `scripts/generate_report.py`. It calls ffprobe on `--original` and
      `--compressed` to get durations, computes removed = original − compressed
      and compression_percentage = (removed / original) × 100 (both rounded to
      2 decimals), loads the `segments` array from the `--segments` JSON (if
      given), and writes the report to `--output`. The script is the source of
      truth for the math.
    script: scripts/generate_report.py
    inputs:
      - name: original-path
        type: string
        description: Path to the original (pre-trim) video. Passed as --original. ffprobe must be able to read it.
      - name: compressed-path
        type: string
        description: Path to the compressed (post-trim) video produced by the processing step. Passed as --compressed. Must exist and be playable.
      - name: segments-path
        type: string
        nullable: true
        description: >
          Path to the removed-segments JSON (e.g. the segment-combiner's
          all_segments.json). Passed as --segments. Its top-level `segments`
          array is copied verbatim into the report. If omitted, or if the file
          has no `segments` key, `segments_removed` is an empty list — which
          fails downstream validation that requires at least one segment, so
          supply a populated segments file.
      - name: output-path
        type: string
        description: Path to write the report JSON. Passed as --output.
    outputs:
      - name: report-json
        type: object
        description: "{original_duration_seconds, compressed_duration_seconds, removed_duration_seconds, compression_percentage, segments_removed: [{start, end, duration, ...}]}. Written to output-path."
  - name: verify-report
    description: >
      Confirm the report is valid before treating the pipeline as done.
      Check: `segments_removed` is non-empty and every entry has `start`, `end`
      (> start), and `duration` (≈ end − start); the duration math is consistent
      (original ≈ compressed + removed); and the segments genuinely describe
      what was cut — the compressed video should be reconstructable by removing
      exactly these segments from the original. Because `segments_removed` is a
      verbatim copy of the input segments JSON, a populated but inaccurate
      segments file yields internally-consistent duration math yet a report that
      misdescribes the cut. If anything is off, fix the upstream segments or
      re-run the processing/detection steps and regenerate. This stays a prose
      step: judging whether the segments faithfully reflect the actual edit
      depends on pipeline context not available to the script as structured data.
    depends_on: [generate-report]
    inputs:
      - name: report-json
        type: object
    outputs:
      - name: final-report-json
        type: object
        description: The accepted report JSON, confirmed structurally valid, math-consistent, and faithful to the actual cut.

scenarios:
  - need: Final step of a trim pipeline — original video, compressed video, and a combined segments JSON all exist.
    action: Run generate_report.py with --original, --compressed, --segments (the combined segments file), and --output.
    outcome: A report with both durations, removed duration, compression percentage, and the segment list — ready as the pipeline's deliverable.
  - need: The report's segments_removed came back empty.
    context: --segments was omitted, pointed at a file with no top-level `segments` array, or that array was itself empty.
    action: Point --segments at the combiner's output (which carries a populated `segments` array) and re-run.
    outcome: segments_removed is populated; structure validation that requires ≥1 segment passes.
  - need: Duration math looks self-consistent but the report seems to misdescribe what was cut.
    context: removed = original − compressed always balances by construction, but segments_removed is a verbatim copy of whatever segments JSON was passed.
    action: Verify the segments file matches the actual edit (regenerate it from the detectors/combiner if not), then regenerate the report.
    outcome: segments_removed faithfully describes the cut, so segment-correspondence and recall/precision checks hold.

integrations:
  - partner: segment-combiner (upstream)
    body: >
      Supplies the segments JSON consumed via --segments. Its output carries a
      top-level `segments` array of `{start, end, duration}` entries, which this
      skill copies verbatim into `segments_removed`. Run it (after the
      detectors) before reporting.
  - partner: video-processor (upstream)
    body: >
      Produces the compressed video this skill measures via --compressed. The
      compressed file must exist and be playable before ffprobe can read its
      duration, so run the processor first.
  - partner: video-silence-remover task (consumer)
    body: >
      The report's shape — original_duration_seconds, compressed_duration_seconds,
      removed_duration_seconds, compression_percentage, segments_removed — is the
      required compression_report.json deliverable. Write --output to the
      expected report path.

anti_patterns:
  - Running before the compressed video exists — ffprobe needs a real, playable --compressed file; produce it with the processing step first.
  - Omitting --segments (or pointing it at a file with no `segments` array) — segments_removed comes back empty and fails validation that requires at least one segment.
  - Assuming the script validates or recomputes segments — it copies the input `segments` array verbatim, so a wrong segments JSON produces a wrong report even though the duration math still balances.
  - Trusting the report when segments_removed doesn't match the actual cut — internally-consistent durations do not guarantee the segments describe the real edit; verify against the produced video.
  - Hard-coding an absolute `/root/.claude/...` script path from the original docs — invoke the bundled `scripts/generate_report.py` by its relative path so the skill stays portable.
```
