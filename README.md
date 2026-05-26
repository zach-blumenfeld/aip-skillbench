# aip-skillbench

This repo extends [SkillsBench](https://www.skillsbench.ai) ([repo](https://github.com/benchflow-ai/skillsbench), [paper](https://www.skillsbench.ai/skillsbench.pdf)) to evaluate [AIP-formatted skills](https://github.com/zach-blumenfeld/aip).

SkillsBench is a containerized benchmark — 84+ tasks across 11 domains, run via the [BenchFlow SDK](https://github.com/benchflow-ai/benchflow) — that measures agent pass rate under three skill conditions: 

1. **no skills** (mode 1), 
2. **human-curated skills** authored offline by domain experts (mode 2).
3. **self-generated skills** authored by the same agent at trial time (mode 3).

See the paper for the comparative findings across model + harness configurations.

**We add two AIP modes here**, both experimental: 
4. **AIP from instruction** (mode 4) and 
5. **AIP from human-curated** (mode 5). 

Both 4 & 5 use Opus 4.7 to author once via the [AIP skill](https://github.com/zach-blumenfeld/aip), commit the result, and mount it across all trials — matching AIP's author-once-consume-many design pattern.

| # | Mode | Skill source |
|---|---|---|
| 1 | `noskill` | none |
| 2 | `human-curated` | task's bundled human-authored skill |
| 3 | `selfgen-skill-creator` | model writes its own skill at trial time (paper-style self-gen) |
| 4 | `aip-from-instruction` | Opus 4.7 authors an AIP skill from `instruction.md` alone, locked & committed |
| 5 | `aip-from-curated` | Opus 4.7 converts the human-authored skill to AIP, locked & committed |


See [skill-modes.md](skill-modes.md) for the full runbook.

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

## Agents & models

The **solver** (the agent attempting each task during `eval`) can be any agent BenchFlow supports. Pass `--agent` to switch:

```bash
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5    --agent claude-agent-acp   # Anthropic (default)
aip-skillbench eval --task 3d-scan-calc --model gpt-5.2-codex       --agent codex-acp          # OpenAI
aip-skillbench eval --task 3d-scan-calc --model gemini-3-flash-preview --agent gemini          # Google
```

Each agent reads its own API key from `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`). The `--model` string is agent-specific.

## Known limitations

- **AIP authoring is Anthropic-only.** `aip-skillbench convert` (modes 4 & 5) shells out to Claude Code (`claude -p`) and defaults to `claude-opus-4-7` per AIP guidance. Authoring with OpenAI / Google models would require an adapter that mounts the AIP skill in those harnesses' prompt format. Solver evaluation is not restricted — see above.

