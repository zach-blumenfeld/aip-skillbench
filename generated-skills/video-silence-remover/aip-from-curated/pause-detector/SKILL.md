---
name: pause-detector
description: Detect pauses and silence in audio using local dynamic thresholds. Use when you need to find natural pauses in lectures, board-writing silences, or breaks between sections. Uses local context comparison to avoid false positives from volume variation.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+, numpy, and scipy. Consumes a precomputed per-second energy JSON (e.g. from an energy-calculator step); does not decode audio/video itself.
---

```yaml
purpose: >
  Detect interior pauses and low-energy gaps within content from precomputed
  per-second energy data, using a LOCAL dynamic threshold. The bundled tool
  (`scripts/detect_pauses.py`) computes a centered moving-average local energy
  level over `window_size` seconds, flags each second whose energy falls below
  local_avg × `threshold_ratio`, groups consecutive flagged seconds into
  `{start, end, duration}` segments, and keeps those at least `min_duration`
  seconds long. Comparing each second to its local surroundings — rather than to
  one global baseline — avoids false positives when the speaker's volume drifts
  across the recording. It emits a segments JSON whose shape matches the
  silence-detector and feeds a downstream segment-combiner. The numeric logic
  lives in the script; this skill finds interior pauses, not the initial opening
  silence.

trigger_when:
  - Finding natural pauses, gaps, or board-writing silences within content.
  - Detecting breaks between sections of a lecture or talk.
  - You have per-second energy data and need the low-energy stretches inside the content (not just the opening).
  - User mentions "analyze the pauses by audio", removing long pauses, or pause detection that must tolerate volume variation.

do_not_use_when:
  - You need the initial opening / pre-roll silence — that is the silence-detector; this skill targets interior pauses relative to local context.
  - You have no precomputed energy data — compute energies first; the script reads an energy JSON, not media.
  - The recording is roughly uniform low energy with no louder speech to contrast against — a local relative threshold has nothing to dip below and will under-detect (an absolute-threshold method fits better).

scope_and_approval: >
  Reads one energy JSON file and writes one pauses JSON to the path passed via
  `--output`. No network access, no audio/video decoding, no in-place mutation
  of the input. Safe to run without prompting.

steps:
  - name: detect-pauses
    description: >
      Run `scripts/detect_pauses.py` over the energy JSON. It computes a
      centered moving-average local energy level over `--window-size` seconds
      (scipy `uniform_filter1d`, mode "nearest" so the series edges are
      extended), flags each second below local_avg × `--threshold-ratio`, then
      groups consecutive flagged seconds from `--start-time` onward into
      `{start, end, duration}` segments (`end` is exclusive; duration = end −
      start) and keeps segments at least `--min-duration` seconds long. A
      trailing low-energy run is closed at the end of the series. Writes the
      result to `--output`. Set `--start-time` to the content-start offset so
      the already-handled opening is not re-counted as a pause.
    script: scripts/detect_pauses.py
    inputs:
      - name: energies-path
        type: string
        description: Path to the energy JSON; must contain an `energies` key (per-second list[float]). Passed as --energies. The script reads only `energies` and uses len(energies) as the timeline length — it does not read total_seconds.
      - name: output-path
        type: string
        description: Path to write the pauses JSON. Passed as --output.
      - name: start-time
        type: integer
        nullable: true
        description: Second at which to begin analysis; earlier seconds are skipped. Default 0. Pass the silence-detector's content-start offset so the opening is not re-detected as a pause.
      - name: threshold-ratio
        type: float
        nullable: true
        description: Fraction of the local average below which a second counts as low energy (energy < local_avg × ratio). Default 0.5. Higher = more aggressive (flags more seconds, more pauses); lower = more conservative. NOTE this is the inverse of the original docs' tuning table — see source/README.md.
      - name: min-duration
        type: integer
        nullable: true
        description: Minimum pause length in seconds; shorter runs are dropped. Default 2. Higher keeps only longer pauses; lower also keeps short ones.
      - name: window-size
        type: integer
        nullable: true
        description: Moving-average window in seconds for the local energy level. Default 30. Smaller = more local context (average adapts quickly); larger = broader context (more stable average).
    outputs:
      - name: pauses-json
        type: object
        description: >
          JSON written to output-path with keys: `method`
          ("local_dynamic_threshold"), `segments` (list of
          `{start, end, duration}`), `total_segments` (int), `total_duration_seconds`
          (sum of segment durations), and `parameters`
          (`threshold_ratio`, `window_size`, `min_duration`, `start_time`).
  - name: review-and-retune
    description: >
      Inspect the result against what the task expects. If pauses are missed,
      raise `--threshold-ratio` toward 1.0 (more aggressive) and/or lower
      `--min-duration`; if speech is wrongly flagged, lower `--threshold-ratio`
      and/or raise `--min-duration`. Adjust `--window-size` to change how local
      the comparison is: a smaller window adapts to immediate surroundings, a
      larger window compares against a broader stretch. Confirm `--start-time`
      covers the opening so it is not re-counted. This stays a prose step
      because the "is this result plausible" judgment depends on task context
      (expected number/length of pauses, the upstream content-start offset) that
      is not available to the script as structured data.
    depends_on: [detect-pauses]
    inputs:
      - name: pauses-json
        type: object
    outputs:
      - name: final-pauses-json
        type: object
        description: The accepted pauses JSON after any re-tuning; ready for the downstream segment-combiner.

scenarios:
  - need: Find natural pauses in a lecture after skipping a detected ~221s opening.
    context: Energy was computed per second (e.g. via energy-calculator) and the opening end was found by silence-detector.
    action: Run with --start-time 221 and defaults (threshold-ratio 0.5, min-duration 2, window-size 30).
    outcome: Interior pauses are returned as {start, end, duration} segments (e.g. ~11 pauses totaling ~28s), with the opening excluded.
  - need: Too few pauses detected — short gaps between sections are being missed.
    action: Raise --threshold-ratio (e.g. 0.6–0.7) so more near-average dips qualify, and/or lower --min-duration to keep shorter gaps.
    outcome: More interior pauses surface; verify speech is not being clipped.
  - need: Speech is being wrongly flagged as pauses during a quiet passage.
    action: Lower --threshold-ratio (e.g. 0.4) so only deeper dips qualify, and/or raise --min-duration.
    outcome: Only genuine low-energy gaps remain.
  - need: Speaker volume drifts across the recording, so a single global threshold over- or under-detects.
    action: Keep the local dynamic threshold (default) and tune --window-size — smaller to track fast volume changes, larger for a steadier baseline.
    outcome: Each second is judged against its neighbors, so detection tracks the drifting volume instead of a fixed cutoff.

integrations:
  - partner: energy-calculator (upstream)
    body: >
      Supplies the energy JSON (per-second `energies` list) that this skill
      consumes via --energies. Run it first; this skill does not read audio or
      video directly.
  - partner: silence-detector (sibling)
    body: >
      Finds the single initial opening/pre-roll silence using a global baseline.
      Complementary to this skill, which finds interior pauses against a local
      moving average. Use silence-detector's detected content-start as this
      skill's --start-time so the opening is not double-counted, then feed both
      results' segments to the segment-combiner.
  - partner: segment-combiner (downstream)
    body: >
      Consumes the segments JSON this skill emits. The `{start, end, duration}`
      segment shape is intentionally compatible with the silence-detector's, so
      pause and opening segments merge before the media is cut.

anti_patterns:
  - Pointing --energies at raw audio/video — the script reads a precomputed energy JSON (`energies` list), not media. Compute energies first.
  - Leaving --start-time at 0 when an opening exists — the opening's low energy may be re-counted as a pause and double-removed downstream. Set --start-time to the content-start offset.
  - Trusting the original docs' "Parameters Tuning" table for threshold_ratio — its aggressive/conservative direction is inverted relative to the code. Higher ratio detects MORE pauses (see source/README.md).
  - Expecting this skill to catch a long sustained silence (much longer than --window-size) in its interior — the local average sinks to match it, so only the transitions near its edges get flagged. Long openings are the silence-detector's job, reached via --start-time.
  - Hard-coding an absolute `/root/.claude/...` script path from the original docs — invoke the bundled `scripts/detect_pauses.py` by its relative path so the skill stays portable.
```
