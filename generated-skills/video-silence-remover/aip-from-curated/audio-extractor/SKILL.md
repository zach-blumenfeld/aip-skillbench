---
name: audio-extractor
description: Extract audio from video files to WAV format. Use when you need to analyze audio from video, prepare audio for energy calculation, or convert video audio to standard format for processing.
compatibility: Requires ffmpeg and Python 3 on PATH.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Extract audio from a video file into a mono 16-bit PCM WAV at a fixed sample
  rate (16 kHz by default), producing a standard, analysis-ready waveform for
  downstream speech, silence, or energy processing. Wraps ffmpeg via
  scripts/extract_audio.py so callers get consistent output regardless of the
  input container or codec.

trigger_when:
  - User wants to extract or pull audio out of a video file.
  - Preparing audio input for energy calculation, silence detection, or speech analysis.
  - Converting video audio into a standard mono PCM WAV format for further processing.
  - A downstream skill or script expects a 16 kHz mono WAV derived from a video.

do_not_use_when:
  - The source is already an audio file in a usable format — call ffmpeg or a resampler directly instead.
  - The downstream task needs stereo audio or a sample rate other than what this skill is configured to emit.
  - The goal is video editing, transcoding, or muxing rather than audio extraction.

steps:
  - name: locate-inputs
    description: Confirm the input video path exists and choose an output path for the WAV file.
  - name: pick-parameters
    description: Decide whether to override the defaults — sample rate (default 16000 Hz) and an optional duration limit in seconds (default full video).
  - name: run-extractor
    description: >
      Invoke scripts/extract_audio.py with --video, --output, and optional
      --sample-rate / --duration. The script shells out to ffmpeg with -vn,
      -acodec pcm_s16le, -ac 1, and -ar <sample-rate>, writing a mono 16-bit
      PCM WAV.
  - name: verify-output
    description: Check that the WAV was written at the output path and that its size is plausible for the input duration before handing it to downstream processing.

decisions:
  - signal: Downstream step only needs a short prefix of the audio (e.g., a preview or a quick silence probe).
    action: Pass --duration <seconds> to cap extraction time and shrink the output file.
  - signal: Downstream analysis requires higher fidelity than 16 kHz mono.
    action: Override with --sample-rate <hz>; the output stays mono PCM 16-bit. If stereo is required, this skill is the wrong tool.
  - signal: ffmpeg is missing or the input container is unsupported.
    action: Surface the ffmpeg error to the user; install ffmpeg or convert the source to a supported container before retrying.

scenarios:
  - need: Extract full audio from a lecture video for energy analysis.
    action: |
      python3 scripts/extract_audio.py \
          --video /path/to/video.mp4 \
          --output /path/to/audio.wav
    outcome: Mono 16 kHz PCM WAV at /path/to/audio.wav ready for energy or silence processing.
  - need: Extract only the first 10 minutes of audio from a long lecture.
    action: |
      python3 scripts/extract_audio.py \
          --video lecture.mp4 \
          --duration 600 \
          --output audio.wav
    outcome: 10-minute mono 16 kHz WAV (audio.wav), much smaller than full-length extraction.

anti_patterns:
  - Re-implementing ffmpeg invocation inline instead of calling scripts/extract_audio.py — loses the standard mono/PCM/16 kHz contract downstream tools rely on.
  - Asking for stereo output from this skill; it always emits mono by design.
  - Skipping --duration on very long videos when only a short prefix is needed, producing oversized WAVs.
```
