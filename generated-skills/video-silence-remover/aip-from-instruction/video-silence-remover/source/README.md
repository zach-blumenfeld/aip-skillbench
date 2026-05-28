# Source & design notes — video-silence-remover

## Origin

Authored from the task instruction alone:
`vendor/skillsbench/tasks/video-silence-remover/instruction.md`. No existing
skill was inspected. This README records how the instruction maps onto the AIP
skill so the mapping is auditable.

## Task in brief

Given a ~10-min teaching video (`data/input_video.mp4`) that has an unnecessary
opening (static frames with noise) and long pauses (> 2s), produce:
1. `compressed_video.mp4` — silence/opening removed, teaching content kept.
2. `compression_report.json` — `{original_duration_seconds,
   compressed_duration_seconds, removed_duration_seconds, compression_percentage,
   segments_removed:[{start,end,duration}]}`.

Evaluated on: files complete & valid; compression rate in range; removed/compressed
duration close to expected; JSON structure & segment values valid; math consistent
(`original ≈ compressed + removed`). Processing must stay under ~10 min.

## Schema choice

`procedure.schema.json` (reused, not drafted). The task is a linear pipeline with
numeric thresholds — a textbook procedure / runbook: detect → review → render →
verify, with conditional/threshold logic pushed into scripts.

## Design decisions

- **Two detectors, by design.** The opening has *noise* audio, so `silencedetect`
  alone misses it; it is visually *static*, so `freezedetect` catches it. Long
  pauses are *silent*, so `silencedetect` catches them. Both passes are required.
  This is the central domain insight and lives in `references/ffmpeg-detection.md`.
- **Opening = leading freeze only.** A mid-lecture freeze (presenter holding
  still while talking) must be kept, so a freeze counts as the opening only when
  it begins within `--opening-max-start` seconds (default 3s).
- **Thresholds/merging/complement/report-math are script-backed**, per AIP best
  practice (anything with "if"/thresholds/numeric caps must be a script). Pure
  logic in `detect_segments.py` is separated from ffmpeg calls so it is
  unit-testable without ffmpeg.
- **Frame-accurate render.** `build_output.py` trims+concats keep segments via a
  single `filter_complex` pass with re-encode (not `-c copy`), so durations match
  the plan and the math stays consistent. This is what keeps `original ≈
  compressed + removed` true and the rendered duration close to planned.
- **Consistency checks are enforced in code.** `build_output.py` exits non-zero
  if the report math, segment bounds, or rendered-vs-planned duration are off,
  giving the agent a hard validation gate (the plan-validate-execute pattern).
- **`compression_percentage` defined as** `removed / original * 100` (rounded to
  2 dp). The instruction's JSON sample leaves it as `<number>`; this is the
  natural reading given the "math consistent" criterion.

## Source-content classification (completeness check)

- Objective: remove silence + non-teaching content → **Mapped** (purpose, steps).
- Inputs `data/input_video.mp4` → **Mapped** (detect step input, scenarios).
- Output `compressed_video.mp4` + `compression_report.json` w/ exact JSON shape
  → **Mapped** (render step outputs; assets/report template; build_output writes
  the exact keys).
- Remove unnecessary opening → **Mapped** (freezedetect + pick_opening).
- Remove long pauses > 2s → **Mapped** (silencedetect `d=2`, `--min-silence`).
- Keep teaching content → **Mapped** (complement keep segments; keep-pad; min-keep).
- Opening is static frames with noise → **Mapped** (two-detector rationale).
- Analyze pauses by audio → **Mapped** (silencedetect).
- Use ffmpeg or Python → **Mapped** (compatibility + scripts).
- Processing < 10 min → **Mapped** (anti_patterns + render preset note).
- Eval criteria (files valid, rate in range, durations close, JSON valid, math
  consistent) → **Mapped** (verify step + build_output checks + reference tuning band).
- **Deliberate drop:** none. The exact expected compression magnitude is video-
  specific and unknowable from the instruction, so the skill ships a sane
  tuning band (~5–35%) and a review loop rather than a hard-coded number.

## Functional-test limitation

`ffmpeg`/`ffprobe` are not installed in the authoring environment, so the
detection/render passes could not be exercised end-to-end here. The pure-Python
plan logic (parse → merge → complement → report math) was unit-tested directly.
A downstream agent with ffmpeg on PATH runs the full pipeline.
