---
name: video-silence-remover
description: Compress a teaching video by removing the unnecessary opening (static frames with audio noise) and long silent pauses (typically > 2 s), then emit a compression_report.json with original/compressed/removed durations, compression percentage, and the exact intervals removed. Use when the input is a single teaching/lecture video file (e.g. data/input_video.mp4) and the deliverables required are compressed_video.mp4 plus compression_report.json in the working directory. Pairs ffmpeg's silencedetect and freezedetect filters with a trim+concat filter graph; teaching content between silences is preserved verbatim.
license: Apache-2.0
compatibility: Requires ffmpeg and ffprobe on PATH (libx264 + aac encoders) and Python 3.9+. No third-party Python packages needed.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Produce a compressed teaching video plus a strictly-formatted JSON report by
  detecting and removing two kinds of dead time: a static / noisy opening and
  any silent pause longer than ~2 seconds. The cut must preserve teaching
  content verbatim, the report must satisfy the schema in the task
  instruction, and the math must be self-consistent
  (original ≈ compressed + removed).

trigger_when:
  - A teaching or lecture video must be auto-compressed by removing silence and the opening.
  - The deliverables are exactly `compressed_video.mp4` and `compression_report.json` in the workspace.
  - The input is a single MP4 (or similar) on disk, default path `data/input_video.mp4`.
  - An evaluator will check JSON schema validity, removed-duration plausibility, and `original ≈ compressed + removed` consistency.

do_not_use_when:
  - The required output is a transcript, summary, captions, or chaptering — those are different tasks.
  - The user wants every short breath/pause removed for "jump cut" style editing — this skill targets only pauses ≳ 2 s.
  - There is no audio track to analyze (audio-driven silence detection won't fire).

scope_and_approval: >
  Write-only inside the workspace: produces `compressed_video.mp4` and
  `compression_report.json` (paths overridable via flags) and may write
  ffmpeg's temp files. Does not modify the input video. No network access
  required. Re-encodes with libx264 / aac so output is not bit-identical to
  the source segments — this is expected.

steps:
  - name: locate-input
    description: >
      Confirm the input video path. Default to `data/input_video.mp4` unless
      the user gave another path. Verify it exists with `ls` / `Read`-stat
      before invoking the script — a missing input is the most common failure
      mode and the cheapest to catch.
  - name: verify-tooling
    description: >
      Check that `ffmpeg` and `ffprobe` are on PATH (`ffmpeg -version`,
      `ffprobe -version`). If either is missing, install via the system
      package manager (`brew install ffmpeg` / `apt-get install -y ffmpeg`)
      before continuing. The script depends only on stdlib + these binaries.
  - name: detect-silence
    description: >
      Detect long silent pauses with `silencedetect=noise=-30dB:d=2`. -30 dB
      tolerates room tone but flags real pauses; the 2 s floor matches the
      "usually > 2 sec" guidance in the instruction. `scripts/process_video.py`
      handles the parsing, including the case where the file ends in silence
      and ffmpeg omits a final `silence_end`.
    depends_on: [locate-input, verify-tooling]
  - name: detect-opening
    description: >
      Detect the static opening with `freezedetect=n=0.003:d=1.0`, but only
      treat a freeze as "opening" if it starts within ~1 s of t=0. This
      prevents a still slide later in the lecture from being misclassified.
      The detected interval `(0, opening_end)` joins the removal list.
    depends_on: [locate-input, verify-tooling]
    parallel: true
  - name: plan-removals
    description: >
      Union and merge the silence intervals and the opening interval into a
      sorted, non-overlapping removal list. Clamp endpoints to the input
      duration. The complement of this list (intervals to keep) becomes the
      cut plan.
    depends_on: [detect-silence, detect-opening]
  - name: run-processor
    description: >
      Run `python scripts/process_video.py --input <video>` from the
      workspace. The script performs steps `detect-silence`, `detect-opening`,
      `plan-removals`, executes the ffmpeg `trim`+`atrim`+`concat`
      filter_complex, and writes both outputs. Defaults already point at
      `compressed_video.mp4` and `compression_report.json` in the CWD; only
      pass `--output` / `--report` if the user specified other locations.
    depends_on: [plan-removals]
  - name: verify-report
    description: >
      Read `compression_report.json` back and check (a) all five top-level
      keys are present, (b) `segments_removed` items each have `start`,
      `end`, `duration`, (c) `original_duration_seconds ≈
      compressed_duration_seconds + removed_duration_seconds` within ~0.2 s
      tolerance, (d) `compression_percentage` is plausible (typically 5–40 %
      for a 10-min teaching video; if it is 0 or > 70 %, jump to the
      `decisions` table).
    depends_on: [run-processor]
  - name: verify-video
    description: >
      `ffprobe` the output to confirm it is a valid playable mp4 whose
      duration matches `compressed_duration_seconds` in the report. The
      script does this automatically (the report's duration is computed from
      ffprobe of the actual output), but spot-check from the agent side.
    depends_on: [run-processor]

decisions:
  - signal: "ffmpeg / ffprobe not on PATH."
    action: "Install before running the script. macOS: `brew install ffmpeg`. Debian/Ubuntu: `apt-get install -y ffmpeg`."
  - signal: "`compression_percentage` is 0 or near-zero but the video clearly contains long pauses."
    action: "Threshold too low. Re-run with `--silence-db -25dB`, then `-20dB`. See references/tuning.md."
  - signal: "Compression > 70% — likely cutting teaching content."
    action: "Threshold too aggressive. Re-run with `--silence-db -35dB` or `-40dB`. Inspect `--verbose` output to confirm."
  - signal: "Opening is still in the output."
    action: "Re-run with `--freeze-noise 0.01` (looser) or `--freeze-min 0.5` (shorter). If the opening has motion, rely on silence detection alone — pass `--skip-opening` and bump `--silence-db` higher."
  - signal: "Script aborts with `No keep segments`."
    action: "The threshold collapsed the whole video to silence. Reset to defaults; if it still fires, the audio track may be silent — pass `--skip-opening` and `--silence-db -50dB` to keep everything except true digital silence."
  - signal: "Encode takes longer than ~5 min."
    action: "Already using `-preset veryfast -crf 23`. If still slow on a long video, the trim+concat graph is the cost — accept it; the 10-min processing budget allows this."
  - signal: "Report math does not balance (original ≠ compressed + removed)."
    action: "Do not hand-edit the JSON. Re-run the script; it derives `removed_duration_seconds` from ffprobe of the actual output, so a mismatch means the script did not complete cleanly."

scenarios:
  - need: "Default invocation against the canonical input path."
    action: "`python scripts/process_video.py --input data/input_video.mp4` from the workspace root."
    outcome: "Writes `compressed_video.mp4` and `compression_report.json` to the workspace, ready for evaluation."
  - need: "Initial run removed ~2% of the video but the lecture has audible long pauses."
    context: "Silence threshold of -30dB didn't catch ambient room tone hovering around -25dB."
    action: "Re-run with `--silence-db -22dB`. Confirm with `--verbose` that the new silence intervals match audible pauses."
    outcome: "compression_percentage rises into a plausible 10–30% band; teaching content unaffected."
  - need: "Opening is animated (motion graphic) so freezedetect does not fire, but the opening is silent."
    action: "Pass `--skip-opening`; the silence in the opening audio is captured by `silencedetect` and removed along with the rest."
    outcome: "Opening removed, no false positives mid-lecture."

anti_patterns:
  - "Hand-editing `compression_report.json` to make the math balance — the script computes `removed_duration_seconds` from ffprobe so any mismatch indicates a real bug, not a rounding issue."
  - "Using `-c copy` to avoid re-encoding. The ffmpeg `trim`+`concat` filter graph requires decoded frames; `-c copy` will either fail or align cuts to keyframes (sloppy boundaries)."
  - "Removing every sub-2-second gap. The instruction says pauses are 'usually > 2 sec'; aggressive jump-cutting damages teaching cadence."
  - "Trusting `silencedetect` alone to catch the opening. A noisy opening can be louder than the silence threshold; that is why `freezedetect` runs in parallel."
  - "Treating any freeze in the video as 'opening'. The detector intentionally only honors freezes that begin within ~1 s of t=0 so mid-lecture still slides are preserved."
  - "Skipping the verify-report step. The evaluator checks JSON structure and math consistency — a single missing key fails the task even if the video is perfect."
  - "Loading `references/tuning.md` on the happy path. Only read it if the report looks off (signals listed under `decisions`)."
```
