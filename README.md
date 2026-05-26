# aip-skillbench

Evaluate AIP-formatted skills against the [SkillsBench](https://www.skillsbench.ai) task corpus. Five evaluation conditions per (task, model) — see [skill-modes.md](skill-modes.md) for the full runbook.

| # | Mode | Skill source |
|---|---|---|
| 1 | `noskill` | none |
| 2 | `human-curated` | task's bundled human-authored skill |
| 3 | `selfgen-skill-creator` | model writes its own skill at trial time (paper-style self-gen) |
| 4 | `aip-from-instruction` | Opus 4.7 authors an AIP skill from `instruction.md` alone, locked & committed |
| 5 | `aip-from-curated` | Opus 4.7 converts the human-authored skill to AIP, locked & committed |

## Layout

```
aip-skillbench/
├── aip_skillbench/                # CLI package
├── generated-skills/              # AIP authoring outputs for modes 4 & 5 (committed)
├── jobs/                          # bench run outputs (gitignored)
├── vendor/skillsbench/            # submodule of benchflow-ai/skillsbench (read-only)
└── .claude/skills/aip/            # cloned by `bootstrap` (gitignored)
```

`vendor/` and `.claude/` are read-only — never write into them. Mode 4 & 5 conversion artifacts go to `generated-skills/<task>/aip-from-{instruction,curated}/<skill>/`.

## Quickstart

```bash
git clone --recurse-submodules git@github.com:zach-blumenfeld/aip-skillbench.git
cd aip-skillbench
uv sync
aip-skillbench bootstrap            # clones AIP into ./.claude/skills/aip
cp .env.example .env                # fill in ANTHROPIC_API_KEY
aip-skillbench --help
```

To update AIP later: `aip-skillbench bootstrap --force`.

## Commands

```bash
# Modes 1, 2, 3 — single command each.
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode noskill
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode human-curated
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-skill-creator

# Modes 4 & 5 — author once (Opus, committed), then eval any model.
aip-skillbench convert --task 3d-scan-calc --from instruction
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-instruction

aip-skillbench convert --task 3d-scan-calc --from curated
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-curated

# Inspect results
aip-skillbench reward jobs/3d-scan-calc-aip-from-curated-claude-haiku-4-5/<timestamp>/
```

See [skill-modes.md](skill-modes.md) for each mode's authoring input, container mount paths, audit signals, and reference runs.
