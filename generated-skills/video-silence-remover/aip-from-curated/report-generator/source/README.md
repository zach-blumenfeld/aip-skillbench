# report-generator — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `report-generator` (the
`aip-from-curated` track for the `video-silence-remover` task). The canonical
original is preserved verbatim at `source/ORIGINAL_SKILL.md`; the curated tool
is copied verbatim to `scripts/generate_report.py`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/generate_report.py` — verbatim copy of the curated report generator
  (ffprobe durations, removed = original − compressed, percentage =
  (removed / original) × 100, segments copied from the input segments JSON,
  JSON output).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the body
  validates against. Bundled locally so the skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a tiny execution
graph: run a deterministic report-generation tool over a video pair plus a
segments file, then judge whether the resulting report is valid and faithful to
the actual cut. That maps cleanly onto the procedure schema (a script-backed
step node plus a prose verification node connected by inputs/outputs).

## The numeric logic is in the script, not prose

All deterministic math — ffprobe duration extraction, `removed = original −
compressed`, `compression_percentage = (removed / original) × 100`, and the
2-decimal rounding — lives in `scripts/generate_report.py`, per AIP best
practice. The body summarizes it in one line and does not restate the formulas
as authoritative prose.

## Added knowledge beyond the original (derived from the script + task)

The original `SKILL.md` documents the CLI, the output shape, and "compression
percentage = (removed / original) × 100". Reading the script surfaces two
non-obvious, script-grounded properties an agent needs to interpret results
correctly, and which the original does not call out:

1. **`segments_removed` is a verbatim copy of the input `segments` array.** The
   script does `data.get("segments", [])` and drops it straight into the report
   — it never recomputes, validates, or sums segment values. So the removed
   *duration* (from ffprobe) and the removed *segments* (from the JSON) are
   independent: the duration math always balances by construction
   (`removed = original − compressed`), but the segment list is only as correct
   as the file you pass. A populated-but-wrong segments file yields a report
   with consistent durations that nonetheless misdescribes the cut.

2. **An absent or `segments`-less file ⇒ empty `segments_removed`.** Because
   `--segments` is optional and defaults to `[]`, omitting it produces an empty
   list. The task's own validation requires at least one segment, so the skill
   must be run with a populated combiner output.

These are captured in the `generate-report` input descriptions, the
`verify-report` step, `scenarios`, and `anti_patterns`. They are *added* (not
dropped) because they are real, script-derived specialized knowledge — not a
change to the curated tool, which is copied verbatim.

The `verify-report` prose step encodes the checks the task evaluation actually
applies (non-empty segments with valid start/end/duration, `original ≈
compressed + removed`, and segment-vs-video correspondence). It stays prose
because judging whether the segments faithfully reflect the real edit depends on
pipeline context not available to the script as structured data — the documented
exception to "back conditional logic with a script".

## Source-content classification (completeness check)

- Title + description (generate compression reports; structured JSON with
  duration stats, compression ratios, segment details) → **Mapped** to
  `description`, `purpose`, `trigger_when`.
- "Use Cases" (compression statistics, structured output reports, documenting
  results) → **Mapped** to `trigger_when`.
- "Usage" + "Parameters" (`--original`, `--compressed`, `--segments` optional,
  `--output`) → **Mapped** to the `generate-report` step's `inputs`
  (with `--segments` marked nullable).
- "Output Format" (original/compressed/removed durations,
  compression_percentage, segments_removed list) → **Mapped** to the step's
  `outputs.report-json`.
- "Dependencies" (Python 3.11+, ffprobe from ffmpeg) → **Mapped** to
  `compatibility` frontmatter.
- "Notes" (uses ffprobe for accurate duration; percentage = (removed/original)
  × 100) → **Mapped** to the `purpose` and the `generate-report` description
  (one-line summary; the script is the source of truth).
- Pipeline role (report is the final step; consumes combined segments and the
  compressed video) → **Mapped** to `integrations`, `do_not_use_when`,
  `scenarios`.
- Hard-coded example path `/root/.claude/skills/report-generator/scripts/...`
  → **Deliberate drop** of the literal path. Generalized to the relative
  `scripts/generate_report.py` so the skill is portable; the absolute mount
  path is environment-specific (called out in `anti_patterns`).
