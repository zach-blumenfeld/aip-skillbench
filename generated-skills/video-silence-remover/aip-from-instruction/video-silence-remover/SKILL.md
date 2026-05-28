---
name: video-silence-remover
description: >
  Remove the unnecessary opening and long silent pauses from a teaching/lecture
  video, keeping the teaching content, and emit a compression report. Use when
  asked to "remove silence", "compress a teaching video", "cut pauses/dead air",
  "trim the opening/intro", or to produce compressed_video.mp4 plus a
  compression_report.json. Drives ffmpeg silencedetect (audio pauses) and
  freezedetect (static opening frames), then trims and concatenates the kept
  segments. Keywords: silence removal, dead-air, pause cutting, lecture
  compression, ffmpeg, ffprobe.
compatibility: Requires ffmpeg and ffprobe on PATH, and Python 3.10+. Designed for Claude Code or similar agents.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compress a teaching video by removing its unnecessary opening (static frames
  with non-speech noise) and its long pauses (silent dead-air, usually > 2s),
  while preserving the teaching content. Produce the trimmed video and a JSON
  compression report whose duration math is internally consistent. The
  domain insight the agent would otherwise miss: the opening needs VISUAL
  (freeze) detection while pauses need AUDIO (silence) detection — silence
  detection alone misses the opening because the opening has noise, not silence.

trigger_when:
  - Asked to remove silence, dead-air, or long pauses from a video.
  - Asked to trim/cut an unnecessary opening or intro from a lecture/teaching video.
  - Asked to produce a compressed_video.mp4 and/or a compression_report.json.
  - A task supplies a ~10-min teaching video and expects silence-removal + a duration report.

do_not_use_when:
  - The goal is editing for content (re-ordering, captions, effects) rather than removing silence/opening.
  - The video has no teaching structure and any cut is acceptable — general video trimming needs no special procedure.

scope_and_approval: >
  Read-only analysis of the input video; writes only the two output files
  (compressed_video.mp4, compression_report.json) into the working directory.
  Never overwrites or deletes the source input. The render re-encodes the
  video; keep ffmpeg presets fast enough that total processing stays well under
  10 minutes for a ~10-min input. No human approval needed for the standard run;
  surface the detection plan before rendering if the previewed compression looks
  implausible.

steps:
  - name: detect-segments
    description: >
      Run scripts/detect_segments.py to probe the input and detect removable
      segments — the leading static opening (ffmpeg freezedetect) and long
      silent pauses (ffmpeg silencedetect) — then write a plan with the
      complementary keep_segments. Defaults target pauses > 2s and a leading
      freeze within the first 3s.
    script: scripts/detect_segments.py
    inputs:
      - name: input_video
        type: string
        description: Path to the source video, e.g. data/input_video.mp4.
    outputs:
      - name: analysis
        type: object
        description: >
          analysis.json — original_duration_seconds, has_audio, removal_segments
          (each with a reason: opening|silence), keep_segments, and a
          compression_percentage_preview.

  - name: review-plan
    description: >
      Read analysis.json and sanity-check before rendering. Confirm a removal
      segment with reason "opening" starts at 0, that pauses > 2s are captured,
      and that keep_segments still cover the bulk of the runtime (teaching
      content preserved). A teaching video typically compresses ~5–35%; if the
      preview is far outside that band or the opening was missed, re-run
      detect-segments with tuned thresholds — see references/ffmpeg-detection.md
      for which flag to move and in which direction.
    depends_on: [detect-segments]
    inputs:
      - name: analysis
        type: object
    outputs:
      - name: approved_plan
        type: object
        description: The analysis.json the agent judges correct enough to render.

  - name: render-and-report
    description: >
      Run scripts/build_output.py to trim+concatenate keep_segments into
      compressed_video.mp4 (single frame-accurate ffmpeg filter_complex pass,
      re-encoded) and write compression_report.json. The script computes the
      report from the plan and runs internal consistency checks, exiting
      non-zero if the math, segment bounds, or rendered-vs-planned duration are
      inconsistent.
    script: scripts/build_output.py
    depends_on: [review-plan]
    inputs:
      - name: input_video
        type: string
      - name: approved_plan
        type: object
    outputs:
      - name: compressed_video
        type: string
        description: compressed_video.mp4 in the working directory.
      - name: compression_report
        type: object
        description: >
          compression_report.json — original_duration_seconds,
          compressed_duration_seconds, removed_duration_seconds,
          compression_percentage, segments_removed[{start,end,duration}].

  - name: verify
    description: >
      Confirm both output files exist in the working directory and that
      build_output.py exited 0 (its checks already enforce
      original ≈ compressed + removed, valid segment bounds, and
      rendered-duration ≈ planned). If it exited non-zero, read the CHECK
      FAILED lines, adjust thresholds in detect-segments, and repeat from
      there. The expected output JSON shape is in assets/report_template.json.
    depends_on: [render-and-report]
    inputs:
      - name: compressed_video
        type: string
      - name: compression_report
        type: object

scenarios:
  - need: A 10-min lecture with a 6s static title card (low hum) and three pauses of 3–8s.
    context: >
      detect_segments.py reports a freeze [0,6] (reason opening) and three
      silences ≥ 2s; preview compression ~12%.
    action: >
      Review passes (opening at 0, pauses caught, teaching kept). Run
      build_output.py; checks pass.
    outcome: >
      compressed_video.mp4 ~528s and compression_report.json with consistent
      math (original ≈ compressed + removed) and four segments_removed.

  - need: Opening not removed — only the silent pauses were cut.
    context: >
      The title card has light dithering noise so freezedetect at -60dB did not
      fire; analysis.json has no segment with reason "opening".
    action: >
      Per references/ffmpeg-detection.md, re-run with --freeze-noise-db -50
      (more tolerant). Opening now detected; re-review, then render.
    outcome: Opening removed; compression back into the expected band.

anti_patterns:
  - Using only silencedetect — it misses the opening, which is noisy (not silent) but visually static.
  - Treating every freeze as the opening; a mid-lecture freeze during active speech is teaching content and must be kept.
  - Stream-copying cuts (-c copy) — keyframe snapping makes durations drift and breaks the report math; re-encode with the trim/concat filter graph instead.
  - Writing compression_report.json by hand and letting the numbers drift from the segments; let build_output.py compute and self-check them.
  - Hard-coding an expected compression percentage; the true amount is video-specific, so review against a band and tune thresholds instead.
  - Re-encoding so slowly the run exceeds ~10 min; keep a fast preset for a ~10-min input.
```
