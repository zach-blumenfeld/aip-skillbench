---
name: energy-calculator
description: "Calculate per-second RMS energy from a WAV audio file via a bundled script, producing an energy profile (per-window values plus min/max/mean/std stats) for downstream silence, pause, or opening detection. Use when you need to analyze audio volume patterns over time or prepare energy data for silence-detection tasks."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+ and numpy. Input must be a 16-bit PCM WAV file; convert video or compressed audio (mp3/m4a) to WAV first.
---

```yaml
purpose: >
  Compute a per-second RMS (root-mean-square) energy profile from a WAV audio
  file using the bundled `scripts/calc_energy.py`. The script slices the audio
  into fixed-length windows (1 second by default), computes
  `sqrt(mean(samples^2))` per window, and writes a JSON profile: an `energies`
  array (one value per window, in order) plus summary `stats`. RMS energy
  correlates with perceived loudness — higher means louder, lower means
  quieter or silent — so the profile is the raw signal that silence, pause, and
  opening detection threshold against. This skill computes energy only; it does
  not itself decide what counts as silence. Thresholding is left to consumer
  skills (silence-detector, pause-detector).

trigger_when:
  - Need a per-second loudness/energy curve of audio over time.
  - Preparing input for silence-detector, pause-detector, or opening detection.
  - Analyzing audio volume patterns to find quiet vs. loud stretches.
  - User mentions audio energy, RMS, energy profile, or "analyze the pauses by audio".

do_not_use_when:
  - You need the actual silence/pause segments — that is silence-detector or pause-detector; this skill only produces the energy curve they consume.
  - You need spectral/frequency analysis — RMS energy is amplitude-only, not spectral.
  - The input is video or compressed audio (mp4/mp3/m4a) — extract a 16-bit PCM WAV first (e.g. via the audio-extractor skill or ffmpeg), then run this.

scope_and_approval: >
  Read-only on the input WAV. Writes exactly one JSON file at the agent-supplied
  `--output` path; performs no network calls and never modifies the audio in
  place. Safe to run without prompting.

steps:
  - name: ensure-wav-input
    description: >
      Confirm the input is a 16-bit PCM WAV file. The script reads frames with
      `np.frombuffer(..., dtype=np.int16)`, so non-16-bit or compressed formats
      produce garbage energies. It also reads all frames as a single stream and
      does not deinterleave channels — mono is expected (the pipeline's
      audio-extractor emits mono 16 kHz). If the source is video or compressed
      audio, extract/convert to a 16-bit PCM WAV first. This stays prose because
      the source format and conversion tool are task-specific.
    inputs:
      - name: audio-source
        type: string
        description: Path to the source audio or video the user wants energy for.
    outputs:
      - name: audio-path
        type: string
        description: Absolute path to a 16-bit PCM WAV file ready for analysis.
  - name: compute-energy-profile
    description: >
      Run `python3 scripts/calc_energy.py --audio <audio-path> --output
      <output-path> [--window-seconds N]`. The script loads the WAV, splits it
      into `window_seconds`-long windows (default 1), computes RMS per window
      (`sqrt(mean(samples^2))`), and writes the JSON profile. The final window
      may be shorter than a full window and is still included as long as it has
      samples.
    script: scripts/calc_energy.py
    depends_on: [ensure-wav-input]
    inputs:
      - name: audio-path
        type: string
        description: Absolute path to the input 16-bit PCM WAV file.
      - name: output-path
        type: string
        description: Path where the energy-profile JSON is written.
      - name: window-seconds
        type: float
        nullable: true
        description: Window size in seconds for each RMS value. Defaults to 1 when omitted.
    outputs:
      - name: energy-profile
        type: object
        description: >
          JSON written to output-path with keys: `sample_rate` (int Hz),
          `window_seconds` (echoes the input — int 1 by default, float when a
          fractional window is passed), `total_seconds` (= number of windows ×
          window_seconds; an integer with whole-second windows, a float for
          fractional windows like 0.5), `energies` (list[float], one RMS value
          per window in time order), and `stats` (object: `min`, `max`, `mean`,
          `std` floats over the energies).

scenarios:
  - need: Find the opening/pre-roll and long pauses in a teaching video so they can be cut.
    context: Audio was first extracted to a 16-bit PCM WAV (e.g. via audio-extractor).
    action: >
      Run calc_energy.py with the default 1-second window to get one energy
      value per second, then hand the profile to silence-detector (opening) and
      pause-detector (mid-video pauses).
    outcome: A per-second energy array those skills threshold against; this skill makes no cut decisions itself.
  - need: Finer time resolution than one value per second.
    action: Pass `--window-seconds 0.5` (or smaller) for sub-second windows. The output array grows proportionally.
    outcome: Higher-resolution energy curve; `total_seconds` is computed from window count × window_seconds.
  - need: Decide where energy is "low" enough to be silence.
    action: >
      Read `stats` (min/max/mean/std) to understand the dynamic range, but do
      the actual thresholding in silence-detector/pause-detector — those skills
      own the baseline, smoothing, and multiplier logic.
    outcome: This skill stays a pure energy producer; threshold tuning lives downstream.

anti_patterns:
  - Feeding non-16-bit-PCM or compressed audio (mp3/m4a) directly — the int16 read misinterprets the bytes and yields meaningless energies. Convert to a 16-bit PCM WAV first.
  - Expecting this skill to output silence/pause segments — it outputs only the energy curve; segment detection belongs to silence-detector and pause-detector.
  - Treating a stereo WAV as analyzed per-channel — the script reads all frames as one int16 stream without deinterleaving, so feed mono audio for a clean curve.
  - Reinventing thresholding here — baseline, smoothing-window, and threshold-multiplier logic lives in the downstream detector skills, not in energy calculation.
```
