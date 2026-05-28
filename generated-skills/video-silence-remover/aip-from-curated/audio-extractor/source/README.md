# audio-extractor — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `audio-extractor` (the
`aip-from-curated` track for the `video-silence-remover` task). The canonical
original is preserved verbatim at `source/ORIGINAL_SKILL.md`; the curated tool
is copied verbatim to `scripts/extract_audio.py`. The `name:` frontmatter is
unchanged (`audio-extractor`) so the mounted skill name matches what the task
expects.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/extract_audio.py` — verbatim copy of the curated extractor
  (ffmpeg `-vn -acodec pcm_s16le -ar <rate> -ac 1 <output> -y`, with optional
  `-t <duration>`).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the body
  validates against, byte-identical to the spec copy. Bundled locally so the
  skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a tiny execution
graph: run a single ffmpeg-backed extraction over a video, then confirm the
output is usable. That is exactly what the procedure schema models (a
script-backed step node plus a prose verify node connected by inputs/outputs).
Consistent with AIP's bias toward schema reuse and with the sibling skills in
this same task (`silence-detector`, etc.), which also compile to `procedure`.

## The encoding logic is in the script, not prose

The fixed ffmpeg invocation (drop video, `pcm_s16le`, resample, downmix to
mono, overwrite) lives in `scripts/extract_audio.py`, per AIP best practice.
The body summarizes the command for the agent's mental model but does not
reimplement it — the script is the source of truth. There is no
conditional/threshold logic to extract: the only branch in the tool is "append
`-t` if a duration was given," which the script already handles from its
`--duration` argument.

## The verify step stays prose (not script-backed)

`verify-output` carries no fixed-input computation: judging whether the WAV is
"what the task needs" (expected duration, the rate a downstream step wants)
depends on task context not available to a deterministic function. It also
encodes the one genuinely non-obvious operational fact below, which is guidance
rather than a calculation. So it is a prose step, matching the
`review-and-retune` precedent in the sibling `silence-detector`.

## Added knowledge beyond the original (derived from the script)

Reading the curated script surfaced two operational facts the original
`SKILL.md` did not state but that are plainly true from the code, and that an
agent needs to interpret behavior correctly:

- **ffmpeg runs with `capture_output=True` and `check=True`.** On failure the
  script raises `CalledProcessError` with ffmpeg's stderr *captured and
  suppressed*, so the agent sees a non-zero exit but no diagnostic. The
  remedy — re-run the bare ffmpeg command without capture — is documented in
  the `verify-output` step, a `scenario`, and an `anti_pattern`.
- **`-y` overwrites the `--output` path unconditionally.** Captured in
  `scope_and_approval` and an `anti_pattern` so the agent does not point
  `--output` at a file it needs to preserve.

These are added (not changes to the tool, which is copied verbatim) because
they are real, script-grounded specialized knowledge.

## Source-content classification (completeness check)

- Title + description (extract audio from video to WAV; analyze audio / prepare
  for energy calculation / convert to standard format) → **Mapped** to
  `description`, `purpose`, `trigger_when`.
- "Use Cases" (speech analysis, energy-calculation prep, standard-format
  conversion) → **Mapped** to `trigger_when`.
- "Usage" + "Parameters" (`--video`, `--output`, `--sample-rate` 16000,
  `--duration`) → **Mapped** to the `extract-audio` step's `inputs` (with
  defaults in descriptions).
- "Output Format" (WAV, PCM 16-bit signed, mono, 16 kHz default) → **Mapped**
  to `purpose`, the `extract-audio` description, and `outputs.wav-path`.
- "Dependencies" (ffmpeg) → **Mapped** to `compatibility` frontmatter.
- "Example" (extract first 10 minutes with `--duration 600`) → **Mapped** to a
  `scenario` and the `extract-audio` description.
- "Notes" (always mono for consistent analysis; 16 kHz sufficient for speech
  and reduces file size; supports any ffmpeg-readable format) → **Mapped** to
  `purpose`, `do_not_use_when`, the `sample-rate`/`video-path` input
  descriptions, and `anti_patterns`.
- Downstream relationship to energy-calculator (16 kHz default matches its
  expected rate) → **Mapped** to `integrations` and the `sample-rate` input
  note. Derived from reading the sibling `energy-calculator` skill; the curated
  audio-extractor only implied it.
- Hard-coded example path `/root/.claude/skills/audio-extractor/scripts/...`
  → **Deliberate drop** of the literal path. Generalized to the relative
  `scripts/extract_audio.py` so the skill is portable; the absolute mount path
  is environment-specific (called out in `anti_patterns`).

No source content was dropped on the merits — only the environment-specific
absolute path was generalized.
