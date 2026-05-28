# pause-detector — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `pause-detector` (the
`aip-from-curated` track for the `video-silence-remover` task). The canonical
original is preserved verbatim at `source/ORIGINAL_SKILL.md`; the curated tool
is copied verbatim to `scripts/detect_pauses.py`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/detect_pauses.py` — verbatim copy of the curated detector
  (centered moving-average local energy via scipy `uniform_filter1d`,
  per-second flagging of energy < local_avg × ratio, grouping into
  `{start, end, duration}` segments, min-duration filter, segments JSON output).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the body
  validates against. Bundled locally so the skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a small
execution graph: run a local-dynamic-threshold detector over precomputed energy
data, then judge whether the result is plausible and optionally re-tune. That is
exactly what the procedure schema models (a script-backed step node plus a prose
review node connected by inputs/outputs).

## Scope (faithful to the curated skill — not the whole pipeline)

The curated skill is a narrow **interior-pause detector**, one of seven sibling
skills in the `video-silence-remover` task (audio-extractor → energy-calculator
→ silence-detector / pause-detector → segment-combiner → report-generator →
video-processor). It finds low-energy gaps *within* content using a local
dynamic threshold and stops there; it does not detect the opening silence
(silence-detector's job, reached here via `--start-time`), combine segments, or
cut video. This conversion preserves that scope deliberately.

## The numeric logic is in the script, not prose

All the deterministic detection math — the `uniform_filter1d` local average,
`is_low_energy = energies < local_avg * threshold_ratio`, consecutive-run
grouping, and the `min_duration` filter — lives in `scripts/detect_pauses.py`,
per AIP best practice. The body does not restate it; the step descriptions are
one-line summaries.

## Corrected: the original "Parameters Tuning" table inverts threshold_ratio

The original `SKILL.md` tuning table reads:

| Parameter | Lower Value | Higher Value |
|-----------|-------------|--------------|
| `threshold_ratio` | More aggressive | More conservative |

This is **backwards relative to the code**, which is the source of truth. The
script flags a second when `energy < local_avg * threshold_ratio`. A *higher*
ratio raises the cutoff, so *more* seconds qualify as low-energy → *more* pauses
detected (more aggressive removal); a *lower* ratio detects fewer (more
conservative). The conversion therefore describes `threshold-ratio` per the code
(higher = more aggressive) in the input description, `review-and-retune`,
`scenarios`, and an `anti_pattern` that explicitly warns against the original
table's direction. This is exactly the kind of doc/code drift AIP validation is
meant to surface at write time.

The other two table rows are correct relative to the code and are preserved:
`min_duration` (higher → longer pauses only) and `window_size` (lower → local
context, higher → broader context).

## Added knowledge beyond the original (derived from the script)

These are true of `detect_pauses.py` and surfaced in the body so an agent
interprets results correctly, though the original prose did not state them:

- **scipy dependency.** Detection uses `scipy.ndimage.uniform_filter1d`, so
  scipy is required in addition to numpy → added to `compatibility`. (The
  original "Dependencies" section does list numpy and scipy; energy-calculator,
  by contrast, needs only numpy.)
- **Reads only `energies`.** The script does `energy_data["energies"]` and uses
  `len(energies)` as the timeline; it never reads `total_seconds`. Noted on the
  `energies-path` input so the agent knows the minimum required key.
- **`end` is exclusive; duration = end − start.** A segment ends at the first
  non-low index. Noted in the step description.
- **Trailing-run handling.** A low-energy run extending to the end of the series
  is closed at `len(energies)`. Noted in the step description.
- **Local threshold under-detects long sustained silence.** Because the
  threshold is relative to a *centered local* moving average, the interior of a
  silence much longer than `window_size` is not flagged (the local average sinks
  to match it; only the transitions near its edges cross the threshold). This is
  by design — the opening silence is the silence-detector's job and is excluded
  here via `--start-time`. Captured in `purpose`, `do_not_use_when`, and an
  `anti_pattern`.
- **Output `parameters` includes `start_time`.** The script writes
  `start_time` into the output `parameters` block; the original "Output Format"
  example omitted it. The output description reflects the actual script.

## Source-content classification (completeness check)

- Title + description ("local dynamic thresholds", natural pauses, board-writing
  silences, breaks between sections, avoid false positives from volume
  variation) → **Mapped** to `description` (kept verbatim), `purpose`,
  `trigger_when`.
- "Use Cases" (natural pauses in lectures, board-writing silences, breaks
  between sections) → **Mapped** to `trigger_when`.
- "Usage" + "Parameters" (`--energies`, `--output`, `--start-time` 0,
  `--threshold-ratio` 0.5, `--min-duration` 2, `--window-size` 30) → **Mapped**
  to the `detect-pauses` step's `inputs` (defaults in descriptions).
- "Output Format" (method, segments, total_segments, total_duration_seconds,
  parameters) → **Mapped** to the step's `outputs.pauses-json` (plus the
  script-derived note that `parameters` also carries `start_time`).
- "How It Works" (load energy → local average → mark < local_avg × ratio →
  group consecutive → filter by min-duration) → **Mapped** to the
  `detect-pauses` description (one-line summary; script is the source of truth).
- "Dependencies" (Python 3.11+, numpy, scipy) → **Mapped** to `compatibility`.
- "Example" (start at 221s; 11 pauses totaling 28s) → **Mapped** to the first
  `scenario`.
- "Parameters Tuning" table → **Mapped** to `review-and-retune`, `scenarios`,
  and `anti_patterns`, with the `threshold_ratio` direction **corrected** (see
  the dedicated note above).
- "Notes" (requires energy-calculator data; use --start-time to skip the
  opening; local threshold adapts to varying speaker volume) → **Mapped** to
  `do_not_use_when`, `integrations`, `scenarios`, and `anti_patterns`.
- Hard-coded example path `/root/.claude/skills/pause-detector/scripts/...` →
  **Deliberate drop** of the literal mount path. Generalized to the relative
  `scripts/detect_pauses.py` so the skill stays portable; the absolute mount
  path is environment-specific (called out in `anti_patterns`).
