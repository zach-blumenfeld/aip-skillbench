# audio-extractor — AIP conversion notes

## Source

- Original SKILL.md: `vendor/skillsbench/tasks/video-silence-remover/environment/skills/audio-extractor/SKILL.md` (mirrored here as `ORIGINAL_SKILL.md`).
- Original `scripts/extract_audio.py` is copied verbatim to the skill root's `scripts/` directory.

## Schema choice

`procedure.schema.json` — the skill is a small, linear procedure (locate inputs → choose params → run extractor → verify output) with a couple of decision branches, which is exactly what the procedure schema covers.

## Mapping from original SKILL.md

- "Audio Extractor" intro + "Use Cases" → `purpose` + `trigger_when`.
- "Usage" + "Parameters" + "Output Format" → `steps` (`pick-parameters`, `run-extractor`) and the two `scenarios`.
- "Dependencies" (ffmpeg) → `compatibility` frontmatter + `decisions` entry for the "ffmpeg missing" signal.
- "Example" → second entry in `scenarios`.
- "Notes" (mono-only, 16 kHz default, ffmpeg-readable formats) → `decisions` (stereo / sample-rate override) and `anti_patterns` (asking this skill for stereo).

## Deliberate drops

- The hard-coded `/root/.claude/skills/audio-extractor/scripts/extract_audio.py` path from the original Usage block is replaced with a relative `scripts/extract_audio.py` reference, since AIP skills resolve resources relative to the skill root. The original absolute path is task-environment-specific and would mislead in any other install location.

## Name

Preserved as `audio-extractor` to match the mounted skill name expected by the parent `video-silence-remover` task.
