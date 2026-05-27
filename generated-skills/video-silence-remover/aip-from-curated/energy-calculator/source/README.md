# source/

Provenance for the AIP-compiled `energy-calculator` skill.

## Contents

- `ORIGINAL_SKILL.md` — verbatim copy of the upstream curated SKILL.md from
  `vendor/skillsbench/tasks/video-silence-remover/environment/skills/energy-calculator/SKILL.md`.
- `procedure.schema.json` — bundled copy of the AIP `procedure` schema this
  skill's body validates against (matches `metadata.aip.schemaId`).

## Schema choice

The curated skill is a short, single-script procedure: load audio → window →
compute RMS → emit JSON. That's a linear procedure with a small decision table,
so the canonical `procedure` schema is a clean fit. No new schema authored.

## Completeness check vs. ORIGINAL_SKILL.md

- **Mapped**
  - One-line description of the skill → `purpose`.
  - "Use Cases" bullets → `trigger_when`.
  - Script invocation, `--audio` / `--output` / `--window-seconds` parameters,
    and output JSON shape → `steps` (load-audio, window-and-compute, summarize,
    emit-json) plus the worked `scenarios`.
  - "How It Works" 4-step recipe → `steps`.
  - Default 1s window and short-final-window handling → `decisions`.
  - "Dependencies" (Python 3.11+, numpy) and WAV-only input → frontmatter
    `compatibility`.
  - "Notes" (RMS ↔ loudness, downstream consumers) → `purpose` framing and
    `anti_patterns`.
- **Deliberate drops**
  - Absolute `/root/.claude/skills/energy-calculator/scripts/calc_energy.py`
    path from the original examples — replaced with the relative path
    `scripts/calc_energy.py` because the install location is environment
    specific and the curated absolute path would mislead under AIP layout.
  - Bare "Example" block — redundant with the worked `scenarios` entries.
- **Schema gaps**: none.
- **Body drops**: none.

## What changed vs. upstream

- Frontmatter gains the AIP block (`metadata.aip.spec`, `metadata.aip.schemaId`)
  and a `compatibility` line. `name` is preserved unchanged so the task's
  mounted skill name still matches.
- Freeform Markdown body replaced by a single fenced YAML block validated
  against `procedure.schema.json`.
- `scripts/calc_energy.py` is copied verbatim.
