---
name: silence-detector
description: Detect initial silence segments in audio/video using energy-based analysis. Use when you need to find low-energy periods at the start of recordings (title slides, setup time, pre-roll silence).
compatibility: Requires Python 3.11+ and numpy. Consumes energy JSON produced by the energy-calculator skill; output is compatible with segment-combiner.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Detect the initial silence segment at the start of a recording by analyzing
  pre-computed per-second energy data. Establish a baseline from the early
  (assumed silent) window, smooth the energy series, and locate the transition
  point where smoothed energy first exceeds the baseline times a threshold
  multiplier. Emit a segments JSON compatible with downstream trimming /
  segment-combination skills.

trigger_when:
  - Finding initial silence at the start of a recording.
  - Detecting pre-roll silence before content begins.
  - Identifying setup or title-card periods on screencasts / lecture captures.
  - Energy data from the energy-calculator skill is already available and a
    silence cut-point is needed.

do_not_use_when:
  - You need to detect mid-recording pauses or arbitrary silence gaps (this
    skill only finds the *initial* silence segment).
  - Raw audio/video is the only input — run energy-calculator first to produce
    the required energies JSON.
  - The initial period is not distinctly quieter than the content; the
    baseline-vs-threshold approach assumes a clear low-energy lead-in.

steps:
  - name: load-energy-data
    description: >
      Read the energy JSON produced by energy-calculator. Expect an object with
      an `energies` array (per-second energy values) and `total_seconds`.
  - name: baseline-from-initial-window
    description: >
      Compute the mean energy over the first `initial_window` seconds
      (default 60). Treat this as the silent-period baseline.
  - name: smooth-energies
    description: >
      Apply a moving-average filter of width `smoothing_window` (default 30)
      across the energy series to suppress short transients. If the series is
      shorter than the window, use the raw energies.
  - name: find-transition-point
    description: >
      Scan the smoothed series and find the first index where the value exceeds
      `baseline * threshold_multiplier` (default multiplier 1.5). That index
      (in seconds) is the end of the initial silence.
  - name: emit-segments-json
    description: >
      Write a JSON file with `method: "energy_threshold"`, a `segments` array
      (a single `{start, end, duration}` entry when silence is detected, empty
      otherwise), `total_segments`, `total_duration_seconds`, and the
      `parameters` used. Format is compatible with segment-combiner.

decisions:
  - signal: Initial silence is being missed (cut-point lands too late).
    action: Decrease `threshold_multiplier` (more sensitive) or decrease
      `smoothing_window` (less smoothing).
  - signal: Speech onset is being clipped (cut-point lands too early, inside
      real content).
    action: Increase `threshold_multiplier` (more conservative) or increase
      `smoothing_window` (more smoothing).
  - signal: Baseline looks contaminated by early speech or noise.
    action: Shorten `initial_window` so the baseline only covers the
      genuinely-silent lead-in.
  - signal: Baseline is too noisy / unstable on short clips.
    action: Lengthen `initial_window` (when the recording actually has a long
      silent intro) to average over more samples.
  - signal: Output `segments` is empty and `total_duration_seconds` is 0.
    action: No clear low-to-high energy transition was found; treat the
      recording as having no detectable initial silence rather than guessing a
      cut-point.

integrations:
  - partner: energy-calculator
    body: >
      Upstream dependency. Produces the `energies.json` input consumed via
      `--energies`. This skill cannot run without it.
  - partner: segment-combiner
    body: >
      Downstream consumer. The `segments` array in this skill's output uses
      the same `{start, end, duration}` shape that segment-combiner expects,
      so the output JSON can be passed straight through.

scenarios:
  - need: Detect initial silence from existing energy data with default
      parameters.
    action: |
      Run:

      ```bash
      python3 /root/.claude/skills/silence-detector/scripts/detect_silence.py \
          --energies energies.json \
          --threshold-multiplier 1.5 \
          --output silence.json
      ```
    outcome: >
      `silence.json` contains the detected initial silence segment (or an
      empty `segments` list when no clear transition is found).
  - need: Understand the output schema before wiring this into a pipeline.
    context: >
      Output JSON shape:
      ```json
      {
        "method": "energy_threshold",
        "segments": [
          {"start": 0, "end": 120, "duration": 120}
        ],
        "total_segments": 1,
        "total_duration_seconds": 120,
        "parameters": {
          "threshold_multiplier": 1.5,
          "initial_window": 60,
          "smoothing_window": 30
        }
      }
      ```
    action: >
      Consume `segments` directly; `parameters` is echoed back for
      traceability of the run.
    outcome: >
      Downstream skills (e.g., segment-combiner) can treat the `segments`
      array as authoritative for the initial-silence cut.

anti_patterns:
  - Running this skill on raw audio/video — it requires energy data from
    energy-calculator first.
  - Treating an empty `segments` list as a failure. It means no clear
    transition was found; do not synthesize a cut-point.
  - Assuming this finds all silence in the recording. It only detects the
    *initial* silence segment.
  - Hand-tuning `threshold_multiplier` without also considering
    `smoothing_window` — both interact with sensitivity.

search_shortcuts:
  - category: CLI invocation
    body: |
      ```bash
      python3 /root/.claude/skills/silence-detector/scripts/detect_silence.py \
          --energies /path/to/energies.json \
          --output /path/to/silence.json \
          [--threshold-multiplier 1.5] \
          [--initial-window 60] \
          [--smoothing-window 30]
      ```
  - category: Parameters
    body: |
      - `--energies` (required): path to energy JSON from energy-calculator.
      - `--output` (required): path to write the result JSON.
      - `--threshold-multiplier` (default 1.5): lower = more sensitive,
        higher = more conservative.
      - `--initial-window` (default 60s): baseline window. Shorter = tighter
        baseline, longer = smoother baseline.
      - `--smoothing-window` (default 30s): moving-average width. Smaller =
        less smoothing, larger = more smoothing.
```
