# aip-skillbench

Evaluate AIP-formatted skills against the SkillsBench task corpus.

Five conditions per (task, model):

| # | Mode | What the agent gets |
|---|---|---|
| 1 | `noskill` | `instruction.md` only |
| 2 | `human-curated` | `instruction.md` + curated skill from `vendor/skillsbench/tasks/<task>/environment/skills/` |
| 3 | `selfgen-skill-creator` | self-gen pass using `skill-creator` skill |
| 4 | `selfgen-aip` | self-gen pass using AIP skill (mounted from `vendor/aip/`) |
| 5 | `aip-from-curated` | preprocess: AIP-convert curated → `generated-skills/<task>/`, then mount that |

## Layout

```
aip-skillbench/
├── aip_skillbench/cli.py          # `aip-skillbench` command
├── configs/                       # experiment YAMLs
├── generated-skills/              # mode-5 conversion outputs (committed)
├── jobs/                          # bench run outputs (gitignored)
├── vendor/
│   └── skillsbench/               # submodule of benchflow-ai/skillsbench (read-only)
└── .claude/skills/aip/            # cloned by `bootstrap` (gitignored)
```

`vendor/` and `.claude/` are read-only — never write into them. All mode-5
conversion artifacts go to `generated-skills/<task>/<skill>/SKILL.md` in
this repo.

## Quickstart

```bash
git clone --recurse-submodules <this-repo>
cd aip-skillbench
uv sync
aip-skillbench bootstrap            # clones AIP into ./.claude/skills/aip
aip-skillbench --help
```

To update AIP later: `aip-skillbench bootstrap --force`.

## Commands

```bash
# Mode 1
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode noskill

# Mode 2
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode human-curated

# Mode 3
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-skill-creator

# Mode 4
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-aip

# Mode 5 — two steps
aip-skillbench convert --task 3d-scan-calc                 # writes generated-skills/3d-scan-calc/
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-curated
```
