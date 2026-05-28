---
name: audio-extractor
description: Extract audio from video files to WAV format. Use when you need to analyze audio from video, prepare audio for energy calculation, or convert video audio to standard format for processing.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires ffmpeg on PATH and Python 3 (stdlib only — argparse, os, subprocess). Shells out to ffmpeg to decode the video; reads a video file and writes a WAV.
---

```yaml
purpose: >
  Extract the audio track from a video file into a standardized WAV
  (mono, 16-bit signed PCM, 16 kHz by default) suitable for downstream audio
  analysis — RMS energy calculation, silence/pause detection, speech
  processing. The bundled tool (`scripts/extract_audio.py`) wraps ffmpeg with
  fixed codec (`pcm_s16le`) and channel (mono) settings, an adjustable sample
  rate, and an optional duration cap, then overwrites the output path. Beyond
  general ffmpeg knowledge it pins the exact output format the analysis
  pipeline expects (mono 16 kHz PCM), so extracted audio drops straight into
  the energy-calculator without a reformatting step.

trigger_when:
  - You have a video file and need its audio for analysis but no separate audio track.
  - Preparing audio for energy calculation or silence/pause detection.
  - Converting video audio to a standard mono 16 kHz WAV for processing.
  - User mentions extracting audio, pulling the soundtrack, or converting video to WAV.

do_not_use_when:
  - The input is already a WAV in the expected format (mono, 16-bit PCM, target sample rate) — extraction would only re-encode.
  - You must preserve stereo channels or full-fidelity / high-sample-rate audio — this tool downmixes to mono and defaults to 16 kHz.
  - ffmpeg is not installed — the script shells out to it; install ffmpeg first.

scope_and_approval: >
  Reads one video file and writes one WAV to the path passed via `--output`,
  using ffmpeg's `-y` flag, which OVERWRITES that path without prompting. No
  network access; no in-place mutation of the input video. Safe to run without
  prompting as long as the output path is not one you need to preserve.

steps:
  - name: extract-audio
    description: >
      Run `scripts/extract_audio.py` over the video. It invokes
      `ffmpeg -i <video> -vn -acodec pcm_s16le -ar <sample-rate> -ac 1 <output> -y`
      — drop the video stream, encode 16-bit signed PCM, resample to the target
      rate, downmix to mono, and overwrite the output. Pass `--duration` to cap
      extraction to the first N seconds (useful for sampling a long recording).
      On success it prints the output path and file size in MB.
    script: scripts/extract_audio.py
    inputs:
      - name: video-path
        type: string
        description: Path to the input video. Any container/codec ffmpeg can read. Passed as --video.
      - name: output-path
        type: string
        description: Path to write the WAV; overwritten if it exists (ffmpeg -y). Passed as --output.
      - name: sample-rate
        type: integer
        nullable: true
        description: Output sample rate in Hz. Default 16000 — matches the energy-calculator's expected rate; keep it unless a downstream step needs higher fidelity. Passed as --sample-rate.
      - name: duration
        type: integer
        nullable: true
        description: Optional cap, in seconds, on how much audio to extract from the start. Omit to extract the full track. Passed as --duration.
    outputs:
      - name: wav-path
        type: string
        description: Path to the written WAV (equals output-path). Mono, 16-bit signed PCM, at sample-rate.
      - name: size-mb
        type: float
        description: Size of the written WAV in MB, printed by the script as a quick sanity signal.
  - name: verify-output
    description: >
      Confirm the WAV was written and is plausible before handing it
      downstream: the output file exists and is non-empty, and (if --duration
      was set) its length is roughly that cap. Two distinct failure modes: a
      FileNotFoundError means the ffmpeg binary is not on PATH — install ffmpeg
      (see compatibility) and re-run; a CalledProcessError means ffmpeg ran but
      exited non-zero, with its stderr captured and suppressed (the script runs
      ffmpeg with capture_output=True) — re-run the same ffmpeg command
      directly, without capture, to read the real error (missing/unreadable
      input, no audio stream, unwritable output path). This stays a prose step
      because "is this output what the task needs" depends on task context
      (expected duration, downstream rate) not available to the script as
      structured data.
    depends_on: [extract-audio]
    inputs:
      - name: wav-path
        type: string
      - name: size-mb
        type: float
    outputs:
      - name: verified-wav-path
        type: string
        description: The accepted WAV path, ready for the energy-calculator.

scenarios:
  - need: You have lecture.mp4 and need its full audio for energy/silence analysis.
    action: Run with --video lecture.mp4 --output audio.wav (defaults — mono, 16 kHz).
    outcome: audio.wav is a mono 16 kHz 16-bit PCM WAV that feeds the energy-calculator unchanged.
  - need: The recording is hours long and you only need to analyze the opening.
    action: Add --duration 600 to extract just the first 10 minutes.
    outcome: A short WAV covering the first 600 s, smaller and faster to process.
  - need: Extraction fails with a CalledProcessError and no useful message.
    context: The script runs ffmpeg with capture_output=True, so ffmpeg's stderr is captured and not printed.
    action: Re-run the underlying ffmpeg command directly (no capture) to surface the real error — bad path, missing audio stream, or unwritable output.
    outcome: The actual ffmpeg error is visible and can be fixed (correct the path, confirm the file has audio, etc.).
  - need: A downstream step needs higher-fidelity audio than 16 kHz.
    action: Pass --sample-rate 44100 (output is still mono 16-bit PCM, just at the higher rate).
    outcome: A 44.1 kHz mono WAV; note the energy-calculator's default expects 16 kHz, so keep rates consistent across the pipeline.

integrations:
  - partner: energy-calculator (downstream)
    body: >
      Consumes the WAV this skill emits to compute per-second RMS energy. Its
      default sample rate (16000) matches this skill's default output, so the
      mono 16 kHz WAV drops in without reformatting. Run audio-extractor first.
  - partner: silence-detector / pause-detector (downstream of energy)
    body: >
      Operate on the energy JSON derived from this WAV, not on the audio
      directly. This skill is the first stage that turns a video into the
      analyzable audio those detectors ultimately depend on.

anti_patterns:
  - Running extraction on a file that is already a mono 16 kHz PCM WAV — it only re-encodes; pass the existing WAV straight to the energy-calculator.
  - Expecting stereo or high-fidelity output — the tool forces mono and defaults to 16 kHz by design for analysis; that is not a bug to work around.
  - Treating a CalledProcessError as opaque — ffmpeg's stderr is captured (capture_output=True), so re-run ffmpeg directly to read the real cause.
  - Pointing --output at a file you need to keep — ffmpeg runs with -y and overwrites it without warning.
  - Mixing sample rates across the pipeline — if you raise --sample-rate here, make sure downstream steps expect that rate (the energy-calculator defaults to 16000).
  - Hard-coding the absolute `/root/.claude/skills/audio-extractor/scripts/...` path from the original docs — invoke the bundled `scripts/extract_audio.py` by its relative path so the skill stays portable.
```
