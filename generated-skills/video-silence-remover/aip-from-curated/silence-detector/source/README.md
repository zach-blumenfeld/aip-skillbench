# silence-detector — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `silence-detector` (the
`aip-from-curated` track for the `video-silence-remover` task). The canonical
original is preserved verbatim at `source/ORIGINAL_SKILL.md`; the curated tool
is copied verbatim to `scripts/detect_silence.py`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/detect_silence.py` — verbatim copy of the curated detector
  (baseline-from-initial-window, moving-average smoothing, first-crossing of
  baseline × multiplier, segments JSON output).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the body
  validates against. Bundled locally so the skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a small
execution graph: run an energy-thresholding detector over precomputed energy
data, then judge whether the result is plausible and optionally re-tune. That
is exactly what the procedure schema models (a script-backed step node plus a
prose review node connected by inputs/outputs).

## The numeric logic is in the script, not prose

All the deterministic detection math — baseline mean over the initial window,
`threshold = baseline * multiplier`, moving-average smoothing, first-crossing
search — lives in `scripts/detect_silence.py`, per AIP best practice. The body
does not restate it.

## The "Parameters Tuning" table is guidance, not a scriptable rule

The original's tuning table (lower/higher value → more/less sensitive, etc.)
describes *which direction to nudge an input* if the result looks wrong. It is
not a computation the script performs — the script already takes these as
arguments with defaults, and there is no objective function it optimizes
against. So the tuning directions are preserved as the `review-and-retune`
step description plus `scenarios` and `anti_patterns`, where the agent reads
them before deciding to re-run. This is the documented exception to "back
conditional logic with a script": the decision input ("is this result
plausible for this recording") is not available as structured data.

## Added knowledge beyond the original (derived from the script)

Functional testing with fresh agents surfaced one non-obvious property of the
bundled detector that the original `SKILL.md` did not document but that is
plainly derivable from the code: smoothing uses a `valid`-mode `np.convolve`,
so the returned offset is an index into the *smoothed* series and can precede
the true content start by up to ~`smoothing-window` seconds. A wide window
therefore blurs and left-shifts the detected boundary, which is actively
harmful for short/sharp openings. This is captured in the
`detect-initial-silence` description, the `review-and-retune` tuning guidance,
and an `anti_pattern`. It is added rather than dropped because it is real,
script-grounded specialized knowledge an agent needs to interpret results
correctly — not a change to the curated tool, which is copied verbatim.

## Source-content classification (completeness check)

- Title + description (detect initial silence via energy analysis;
  title slides / setup / pre-roll) → **Mapped** to `description`, `purpose`,
  `trigger_when`.
- "Use Cases" (initial silence, pre-roll, setup/title periods) → **Mapped** to
  `trigger_when`.
- "Usage" + "Parameters" (`--energies`, `--output`, `--threshold-multiplier`
  1.5, `--initial-window` 60, `--smoothing-window` 30) → **Mapped** to the
  `detect-initial-silence` step's `inputs` (with defaults in descriptions).
- "Output Format" (method, segments, total_segments, total_duration_seconds,
  parameters) → **Mapped** to the step's `outputs.silence-json`.
- "How It Works" (load energy → baseline → smooth → first crossing) →
  **Mapped** to the step description (one-line summary; the script is the
  source of truth).
- "Dependencies" (Python 3.11+, numpy) → **Mapped** to `compatibility`
  frontmatter.
- "Parameters Tuning" table → **Mapped** to `review-and-retune`, `scenarios`,
  and `anti_patterns` (see note above on why it is guidance, not a script).
- "Notes" (requires energy-calculator data; works best with distinctly lower
  initial energy; returns empty if no transition; output compatible with
  segment-combiner) → **Mapped** to `do_not_use_when`, `integrations`,
  `scenarios`, and `anti_patterns`.
- pause-detector format compatibility (script comment "same format as pause
  detector") → **Mapped** to an `integrations` entry.
- Hard-coded example path `/root/.claude/skills/silence-detector/scripts/...`
  → **Deliberate drop** of the literal path. Generalized to the relative
  `scripts/detect_silence.py` so the skill is portable; the absolute mount
  path is environment-specific (called out in `anti_patterns`).
