---
name: video-processor
description: Process videos by removing segments and concatenating remaining parts. Use when you need to remove detected pauses/openings from videos, create highlight reels, or batch process segment removals using ffmpeg filter_complex.
compatibility: Requires ffmpeg with libx264 and aac support, Python 3.11+, and sufficient disk space (output ≈ 70–80% of input size).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Remove specified time-range segments from a video and concatenate the
  remaining parts into a single output file. Wraps
  `scripts/process_video.py`, which builds an ffmpeg `filter_complex`
  pipeline to trim audio and video together, re-encodes with libx264
  (CRF 23) plus AAC audio, and emits a JSON report summarizing
  compression and segment counts.

trigger_when:
  - User wants to remove detected pauses, silences, or opening segments from a video.
  - User wants to build a highlight reel by dropping specific time ranges.
  - User has one or more JSON files listing segments to remove and an input video.
  - User asks to batch-process multiple removal segment files against the same video.

do_not_use_when:
  - The required cut is sample-accurate (this pipeline is frame-accurate, not sample-accurate).
  - No ffmpeg/libx264/aac install is available in the environment.
  - The user wants to keep specific segments rather than remove them and has no removal list — invert upstream first.

scope_and_approval: >
  Writes a new output video and a sibling `<output>_report.json`. Does
  not modify the input. Long-running (~0.3× video duration). Confirm
  the output path before invoking on large files to avoid overwriting
  prior runs — the script passes `-y` to ffmpeg and will overwrite
  silently.

steps:
  - name: prepare-segments
    description: >
      Collect one or more removal-segment JSON files. Each file is
      either `{"segments": [{"start": s, "end": e, "duration": d}, ...]}`,
      a bare list of segment objects, or a single segment object.
      `start`/`end` are seconds from the video start; `duration` is
      optional metadata used for reporting totals. Segments may come
      from multiple files (e.g., one for the opening, one for detected
      pauses); the script concatenates and sorts them by `start`.
  - name: invoke-processor
    description: |
      Run the processor with the input video, desired output path, and
      one or more removal-segment files:

          python3 /root/.claude/skills/video-processor/scripts/process_video.py \
              --input /path/to/input.mp4 \
              --output /path/to/output.mp4 \
              --remove-segments /path/to/segments.json [more.json ...]

      The script probes input duration via `ffprobe`, computes the
      keep-segments as the inverse of the removal list, builds the
      `filter_complex` graph, and re-encodes with `-c:v libx264
      -preset medium -crf 23 -c:a aac -b:a 128k`. Expect ~0.3× the
      input duration in wall time on a 2+ core machine.
    depends_on: [prepare-segments]
  - name: verify-output
    description: |
      Read the generated `<output>_report.json` and confirm the
      numbers match expectations. The report shape is:

          {
            "original_duration": 3908.61,
            "output_duration": 3078.61,
            "removed_duration": 830.0,
            "compression_percentage": 21.24,
            "segments_removed": 91,
            "segments_kept": 91
          }

      `segments_kept` is the count of inverse keep-segments, not the
      count of removal segments. If `compression_percentage` is far
      from the expected total of segment `duration`s ÷ original
      duration, the removal list was probably wrong (overlapping
      ranges, off-by-one ends, or a stray full-video removal).
    depends_on: [invoke-processor]

decisions:
  - signal: User wants different quality/size trade-off.
    action: Edit `scripts/process_video.py` to change `-preset` (slower → better compression) and `-crf` (lower → higher quality, larger file). `-preset medium` + `-crf 23` is the bundled default.
  - signal: Cut occurs mid-frame and audio/video drift is suspected.
    action: Treat as a frame-accuracy limit, not a bug. If sample-accurate cuts are required, this script is the wrong tool — use a different pipeline.
  - signal: Output file size is unexpectedly large or small.
    action: Verify `crf` and `preset` were not overridden; check that the segment list actually removed what was intended by re-reading `<output>_report.json`.
  - signal: ffmpeg fails or `subprocess.run` raises.
    action: Re-run the same `ffmpeg` command manually without `capture_output=True` to see the underlying error. Most failures are missing codecs, an unwritable output path, or a segment whose `end` exceeds the video duration.

scenarios:
  - need: Compress a 65-minute lecture by removing the opening and detected pauses.
    context: |
      Two segment files exist: `opening.json` covering 0–600s, and
      `pauses.json` listing ~90 short pauses scattered through the
      lecture. Combined removal totals ~830s.
    action: |
      Invoke:

          python3 /root/.claude/skills/video-processor/scripts/process_video.py \
              --input /root/lecture.mp4 \
              --output /root/compressed.mp4 \
              --remove-segments /root/opening.json /root/pauses.json
    outcome: 65 min → 51 min output (~21.2% compression). Report written to `/root/compressed_report.json`.
  - need: Debug an unexpected filter_complex error.
    context: |
      For 3 keep-segments, the script generates a filter graph of this
      shape (start/end values are illustrative):

          [0:v]trim=start=600:end=610,setpts=PTS-STARTPTS[v0];
          [0:a]atrim=start=600:end=610,asetpts=PTS-STARTPTS[a0];
          [0:v]trim=start=613:end=1000,setpts=PTS-STARTPTS[v1];
          [0:a]atrim=start=613:end=1000,asetpts=PTS-STARTPTS[a1];
          [v0][v1]concat=n=2:v=1:a=0[outv];
          [a0][a1]concat=n=2:v=0:a=1[outa]
    action: Print the generated filter (add a `print(filter_complex)` before the `subprocess.run` call) and re-run ffmpeg directly with that filter to isolate the syntax error from the surrounding orchestration.

anti_patterns:
  - Passing keep-segments instead of remove-segments — the `--remove-segments` flag is the inverse of what the script outputs. Invert upstream if you only have a keep list.
  - Letting two removal files overlap without checking. The script sorts by `start` but does not merge overlapping ranges, so an overlap leaves a gap of zero-length keep-segment and may produce a filter ffmpeg refuses.
  - Running the script on a machine without 2+ CPU cores and expecting the ~0.3× wall-time figure — encoding throughput scales with cores.
  - Re-running with the same `--output` path expecting a prompt; ffmpeg `-y` overwrites silently.
```
