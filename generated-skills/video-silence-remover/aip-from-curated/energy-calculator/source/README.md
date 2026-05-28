# energy-calculator — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `energy-calculator` (the
`aip-from-curated` track for the `video-silence-remover` task). The canonical
original is preserved verbatim at `source/ORIGINAL_SKILL.md`; the curated tool
is copied verbatim to `scripts/calc_energy.py`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/calc_energy.py` — verbatim copy of the curated tool (loads a WAV,
  slices into windows, computes per-window RMS, writes a JSON energy profile
  with summary stats).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the body
  validates against. Bundled locally so the skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a small
execution graph: ensure a usable WAV input → run the energy script → produce a
JSON profile that downstream skills consume. That is exactly what the procedure
schema models (a script-backed step node connected by inputs/outputs).

## Scope (faithful to the curated skill — not the whole pipeline)

The curated skill is a narrow **energy producer**, one of seven sibling skills
in the `video-silence-remover` task (audio-extractor → energy-calculator →
silence-detector / pause-detector → segment-combiner → report-generator →
video-processor). It computes the per-second RMS energy curve and stops there;
it does not detect silence, choose thresholds, or cut video. This conversion
preserves that scope deliberately. Threshold/baseline/smoothing logic belongs to
silence-detector and pause-detector and is intentionally **not** pulled in here.

## Why the steps are script-backed (and one is prose)

`compute-energy-profile` is backed by `scripts/calc_energy.py` — all the real
logic (windowing, the `sqrt(mean(samples^2))` RMS math, stats) lives in the
script, which is the source of truth. `ensure-wav-input` is kept as prose: it
has no fixed algorithm because the source format and the right conversion tool
are task-specific (could be ffmpeg, the audio-extractor skill, etc.). It exists
to surface a non-obvious requirement read off the script — see below.

## Knowledge derived from reading the script (beyond the curated prose)

These gotchas are not stated in the original `SKILL.md` but are true of
`calc_energy.py` and are surfaced in the body so an agent gets them right:

- **16-bit PCM assumption.** The script reads frames as `np.int16`. Non-16-bit
  or compressed audio is misinterpreted and yields meaningless energies →
  captured in `compatibility`, `do_not_use_when`, `ensure-wav-input`, and an
  anti-pattern.
- **No channel deinterleaving.** All frames are read as one int16 stream, so a
  stereo WAV interleaves L/R. Mono is expected → noted in `ensure-wav-input`
  and an anti-pattern.
- **Partial final window.** The loop includes the last window even if shorter
  than `window_seconds`, as long as it has samples → noted in
  `compute-energy-profile`.

## Source-content classification (completeness check)

- Title + description + "Use Cases" (energy for silence detection, prep for
  opening/pause detection, volume-pattern analysis) → **Mapped** to
  `description`, `purpose`, and `trigger_when`.
- "Usage" (command + `--audio` / `--output` / `--window-seconds` params, default
  1) → **Mapped** to `compute-energy-profile` (script + inputs; window-seconds
  marked nullable with default noted).
- "Output Format" JSON (`sample_rate`, `window_seconds`, `total_seconds`,
  `energies`, `stats{min,max,mean,std}`) → **Mapped** to the `energy-profile`
  output description.
- "How It Works" (load → 1-second windows → RMS `sqrt(mean(samples^2))` → array)
  → **Mapped** to the `compute-energy-profile` description; the script is the
  source of truth for the math.
- "Dependencies" (Python 3.11+, numpy) → **Mapped** to `compatibility`.
- "Example" → **Mapped** to `compute-energy-profile` + the first `scenario`.
- "Notes" (RMS correlates with loudness; higher = louder, lower = quieter;
  output used by opening-detector and pause-detector) → **Mapped** to `purpose`,
  `scenarios`, and `anti_patterns`.
- Hard-coded path `/root/.claude/skills/energy-calculator/scripts/...` →
  **Deliberate drop** of the literal mount path. Generalized to
  `scripts/calc_energy.py` (relative to the skill root) so the skill is
  portable; the absolute mount path is environment-specific.
