---
name: pause-detector
description: Detect pauses and silence in audio using local dynamic thresholds. Use when you need to find natural pauses in lectures, board-writing silences, or breaks between sections. Uses local context comparison to avoid false positives from volume variation.
compatibility: Requires Python 3.11+, numpy, and scipy. Consumes pre-computed energy JSON produced by the energy-calculator skill.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Detect pauses and low-energy segments in audio by applying a local dynamic
  threshold to pre-computed per-second energy values. Comparing each second to
  a sliding-window local average (rather than a single global cutoff) keeps
  detection robust when the speaker's volume varies across the recording.

trigger_when:
  - User wants to find natural pauses in a lecture or talk.
  - User wants to detect board-writing silences or other long quiet stretches.
  - User wants to identify breaks between sections of a recording.
  - Pre-computed per-second energy data (from energy-calculator) is already available.

do_not_use_when:
  - Energy data has not been produced yet — run energy-calculator first.
  - A single global silence threshold is acceptable (use a simpler tool).
  - The task is general voice-activity detection on raw audio rather than pause segmentation from energies.

steps:
  - name: load-energies
    description: Read the energy JSON file passed via --energies and extract the `energies` array (one value per second).
  - name: compute-local-average
    description: Apply a sliding-window uniform filter of size --window-size (default 30) over the energies to get a local average per second.
  - name: mark-low-energy
    description: Flag each second where energy < local_avg × --threshold-ratio (default 0.5) as low-energy.
  - name: group-segments
    description: Walk the low-energy mask from --start-time onward and group consecutive low-energy seconds into contiguous segments with start, end, and duration.
  - name: filter-by-duration
    description: Drop any segment whose duration is below --min-duration seconds (default 2).
  - name: write-output
    description: Write a JSON file to --output containing method, segments, total_segments, total_duration_seconds, and the parameters used.

decisions:
  - signal: Too many short false-positive pauses are detected.
    action: Lower --threshold-ratio (more conservative) and/or raise --min-duration to only keep longer pauses.
  - signal: Real pauses are being missed.
    action: Raise --threshold-ratio (more aggressive) and/or lower --min-duration to admit shorter pauses.
  - signal: Speaker volume changes across the recording cause uneven detection.
    action: Adjust --window-size — smaller for tighter local context, larger for broader smoothing.
  - signal: A known opening segment (intro, title card) should be skipped.
    action: Pass --start-time set to the second the analyzable content begins.
  - signal: Required energy JSON is missing.
    action: Run the energy-calculator skill first to produce the energies file, then re-invoke this skill.

integrations:
  - partner: energy-calculator
    body: |
      Upstream dependency. energy-calculator produces the per-second energy JSON
      that this skill consumes via --energies. The expected input shape is
      `{"energies": [<float>, <float>, ...]}` with one value per second.

scenarios:
  - need: Detect pauses in a lecture after skipping the opening segment.
    context: Opening detected to end at second 221; energies.json already produced by energy-calculator.
    action: |
      Run:
        python3 scripts/detect_pauses.py \
          --energies energies.json \
          --start-time 221 \
          --output pauses.json
    outcome: pauses.json reports 11 pauses totaling 28 seconds, each with start/end/duration.

anti_patterns:
  - Using a single global threshold across the whole recording when speaker volume varies — produces false positives in loud sections and misses pauses in quiet ones.
  - Running this skill before energy-calculator has produced the energies JSON.
  - Setting --min-duration too low and treating every breath gap as a pause.
  - Forgetting --start-time and re-detecting the intro as a pause region.
```
