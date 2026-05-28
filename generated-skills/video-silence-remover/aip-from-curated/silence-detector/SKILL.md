---
name: silence-detector
description: Detect initial silence segments in audio/video using energy-based analysis. Use when you need to find low-energy periods at the start of recordings (title slides, setup time, pre-roll silence).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+ and numpy. Consumes a precomputed energy JSON (e.g. from an energy-calculator step); does not decode audio/video itself.
---

```yaml
purpose: >
  Detect the single initial low-energy silence segment at the start of a
  recording (title slide, setup time, static opening, pre-roll silence) from
  precomputed per-second energy data. The bundled tool
  (`scripts/detect_silence.py`) establishes a baseline from the first N
  seconds — assumed silent — smooths the energy series with a moving average,
  and reports the first offset where smoothed energy exceeds
  baseline × multiplier as the end of the silence. It emits a segments JSON
  whose `{start, end, duration}` shape is compatible with a downstream
  segment-combiner. The numeric detection logic lives in the script; this skill
  finds only the opening silence, not interior pauses.

trigger_when:
  - Finding the initial / pre-roll silence at the start of a recording.
  - Detecting a setup, title-card, or static-opening period before content begins.
  - You have per-second energy data and need the offset where real content starts.
  - User mentions removing an opening, pre-roll silence, or a low-energy intro from audio/video.

do_not_use_when:
  - You need pauses or gaps in the middle of content — that is the pause-detector's job; this skill returns only the single initial silence segment.
  - You have no precomputed energy data — compute energies first; the script reads an energy JSON, not media.
  - The opening is not distinctly quieter than the content — with no clear energy transition, detection legitimately returns empty.

scope_and_approval: >
  Reads one energy JSON file and writes one silence JSON to the path passed via
  `--output`. No network access, no audio/video decoding, no in-place mutation
  of the input. Safe to run without prompting.

steps:
  - name: detect-initial-silence
    description: >
      Run `scripts/detect_silence.py` over the energy JSON. It computes a
      baseline mean from the first `--initial-window` seconds, smooths the
      energy series with an `--smoothing-window` moving average, and takes the
      first offset where smoothed energy exceeds baseline × `--threshold-multiplier`
      as the end of the initial silence. Writes the result to `--output`. An
      empty `segments` list (silence end = 0) is the valid output when no clear
      transition is found. Smoothing is a `valid`-mode moving average, so the
      reported end can precede the true content start by up to roughly
      `--smoothing-window` seconds; shrink the window for a crisper,
      better-aligned boundary.
    script: scripts/detect_silence.py
    inputs:
      - name: energies-path
        type: string
        description: Path to the energy JSON; must contain `energies` (per-second list[float]) and `total_seconds`. Passed as --energies.
      - name: output-path
        type: string
        description: Path to write the silence JSON. Passed as --output.
      - name: threshold-multiplier
        type: float
        nullable: true
        description: Baseline multiplier defining the silence/content boundary. Default 1.5. Lower = more sensitive, higher = more conservative.
      - name: initial-window
        type: integer
        nullable: true
        description: Seconds of the (assumed-silent) opening used to compute the baseline. Default 60. Shorter = tighter baseline.
      - name: smoothing-window
        type: integer
        nullable: true
        description: Moving-average window in seconds. Default 30. Larger = more smoothing of transient spikes.
    outputs:
      - name: silence-json
        type: object
        description: "{method, segments: [{start, end, duration}], total_segments, total_duration_seconds, parameters, analysis}. Written to output-path."
      - name: silence-end
        type: integer
        description: Offset in seconds where content begins (the silence segment's end). 0 when no transition is detected.
  - name: review-and-retune
    description: >
      Inspect the result against what the task expects. If `total_segments` is 0
      but an opening clearly exists, or the detected end is implausible, re-run
      step 1 with adjusted parameters per the tuning guidance: lower
      `--threshold-multiplier` for more sensitivity, shorten `--initial-window`
      so the baseline isn't polluted by content, or adjust `--smoothing-window`
      — raise it to ride over transient spikes, but lower it for a short or
      sharp opening, where a wide window blurs and left-shifts the detected
      boundary. This stays a prose step because the
      "is this result plausible" judgment depends on task context (expected
      opening length) that is not available to the script as structured data.
    depends_on: [detect-initial-silence]
    inputs:
      - name: silence-json
        type: object
      - name: silence-end
        type: integer
    outputs:
      - name: final-silence-json
        type: object
        description: The accepted silence JSON after any re-tuning; ready for the downstream segment-combiner.

scenarios:
  - need: The first N seconds are a silent/static opening and the content has distinctly higher energy.
    action: Run with defaults (threshold-multiplier 1.5, initial-window 60, smoothing-window 30).
    outcome: silence-end is the content-start offset; segments holds one entry spanning 0 to silence-end.
  - need: Detection returns total_segments 0 / silence-end 0.
    context: No smoothed energy point exceeded baseline × multiplier — either no initial silence, the opening isn't distinctly quieter, or the multiplier is too high.
    action: Confirm an opening actually exists; if so, lower --threshold-multiplier and/or shorten --initial-window, then re-run.
    outcome: A transition is found when the opening is genuinely lower-energy; the empty result stands when it isn't.
  - need: The baseline window is longer than the actual opening, so it absorbs loud content and inflates the threshold.
    action: Shorten --initial-window to cover only the silent intro.
    outcome: Baseline reflects true silence; the threshold is no longer over-inflated and the transition surfaces.
  - need: The detected end is unstable because of short energy spikes within the opening.
    action: Increase --smoothing-window for a longer moving average.
    outcome: Transient spikes are smoothed out; the detected transition is stable.

integrations:
  - partner: energy-calculator (upstream)
    body: >
      Supplies the energy JSON (per-second `energies` list plus `total_seconds`)
      that this skill consumes via --energies. Run it first; this skill does not
      read audio or video directly.
  - partner: segment-combiner (downstream)
    body: >
      Consumes the segments JSON this skill emits. The `{start, end, duration}`
      segment shape is intentionally compatible, so the initial-silence segment
      merges with other removable segments before the media is cut.
  - partner: pause-detector (sibling)
    body: >
      Finds interior pauses (long gaps) within content and emits the same
      segment shape. Complementary to this skill's initial-silence detection;
      both feed the segment-combiner.

anti_patterns:
  - Pointing --energies at raw audio/video — the script reads a precomputed energy JSON (`energies` + `total_seconds`), not media. Compute energies first.
  - Using this skill to find mid-content pauses — it returns only the single initial silence segment; use the pause-detector for interior gaps.
  - Treating an empty `segments` result as a failure — it is the documented, valid output when there's no clear initial-silence-to-content transition.
  - Leaving --initial-window at 60 when the opening is much shorter — the baseline then includes content and inflates the threshold, hiding the transition. Match the baseline window to the silent intro.
  - Leaving --smoothing-window at 30 for a short or sharp opening — the wide moving average blurs the transition and shifts the detected end earlier; shrink it to pinpoint a crisp boundary.
  - Hard-coding an absolute `/root/.claude/...` script path from the original docs — invoke the bundled `scripts/detect_silence.py` by its relative path so the skill stays portable.
```
