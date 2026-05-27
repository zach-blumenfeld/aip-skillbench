---
name: energy-calculator
description: Calculate per-second RMS energy from audio files. Use when you need to analyze audio volume patterns, prepare data for silence/pause detection, or create an energy profile for audio analysis tasks.
compatibility: Requires Python 3.11+ and numpy. Input audio must be a WAV file.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Calculate per-second RMS (Root Mean Square) energy from a WAV audio file and
  emit a JSON energy profile (sample rate, per-window energies, and summary
  stats). The output feeds downstream silence detection, opening detection, and
  pause detection workflows where perceived loudness over time is the relevant
  signal.

trigger_when:
  - Analyzing audio volume patterns over time.
  - Preparing input for silence, pause, or opening detection.
  - Producing an energy profile JSON for another audio-analysis skill to consume.
  - User mentions RMS energy, audio energy, or loudness profile of a WAV file.

do_not_use_when:
  - Input is a non-WAV format (MP4, MP3, etc.) — extract WAV audio first.
  - Frequency-domain analysis is required (use an FFT-based tool instead).
  - Sub-second timing precision finer than the configured window is needed.

steps:
  - name: load-audio
    description: Open the WAV file at --audio with the `wave` module; read frames and decode as int16 PCM into a float32 numpy array. Capture the sample rate.
  - name: window-and-compute
    description: "Split the sample array into fixed-size windows of `sample_rate * --window-seconds` samples. For each non-empty window compute RMS = sqrt(mean(samples^2)) and append to the energies list."
  - name: summarize
    description: Compute min, max, mean, and std over the energies list. Derive total_seconds as len(energies) * window_seconds.
  - name: emit-json
    description: "Write a JSON document to --output with keys: sample_rate, window_seconds, total_seconds, energies, and stats."

decisions:
  - signal: Caller did not pass --window-seconds.
    action: Default to a 1-second window.
  - signal: Final window has fewer samples than window_size.
    action: Still compute RMS over the short window (skip only if it is empty).
  - signal: Downstream skill expects per-second granularity.
    action: Keep the default 1-second window so indices in `energies` map directly to seconds.

scenarios:
  - need: Generate an energy profile for silence detection on an extracted audio track.
    action: "Run `python3 scripts/calc_energy.py --audio audio.wav --output energies.json` and pass `energies.json` to the silence/pause detector."
    outcome: JSON with per-second RMS values and summary stats suitable for thresholding.
  - need: Inspect loudness range of a recording before choosing a silence threshold.
    context: User wants to know the min/max/mean energy before tuning a downstream cutoff.
    action: Run the script and read the `stats` block from the output JSON.
    outcome: stats.min, stats.max, stats.mean, stats.std reported alongside the full energies array.

anti_patterns:
  - Treating RMS energy as an absolute loudness measurement — it is relative to the recording's bit depth and gain.
  - Using a sub-second window when downstream consumers index by second.
  - Feeding non-WAV audio directly; the script uses the `wave` module and will fail on other containers.
  - Interpreting low energy as definitive silence without a threshold tuned against this recording's stats.
```
