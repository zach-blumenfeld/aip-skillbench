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

# Author modes 4 & 5 in bulk — parallel claude -p calls, skips already-done outputs.
aip-skillbench batch-convert --task 3d-scan-calc --task earthquake-phase-association \
                             --from both --concurrency 4
# Or convert all 95 tasks at once (default pattern is "*"):
aip-skillbench batch-convert --from both --concurrency 4

# Inspect results
aip-skillbench reward jobs/3d-scan-calc-aip-from-curated-claude-haiku-4-5/<timestamp>/
```

See [skill-modes.md](skill-modes.md) for each mode's authoring input, container mount paths, audit signals, and reference runs.

To sweep many `(task × model × mode × trial)` combinations concurrently with live progress, see [run-matrix.md](run-matrix.md). To regenerate the AIP skill cohort against a new spec version, see [scripts/regenerate-aip-cohort.md](scripts/regenerate-aip-cohort.md).

### `batch-convert` flags

| flag | default | notes |
|---|---|---|
| `--task` (repeatable) | — | Task name(s). Required unless `--pattern` is given. |
| `--pattern` | `*` | Glob filter on task names. Ignored if any `--task` is set. |
| `--from` | `both` | `instruction`, `curated`, or `both` (= 2× authoring calls per task). |
| `--concurrency` / `-j` | 4 | Parallel `claude -p` calls. Real ceiling is the Anthropic per-org rate limit for `claude-opus-4-7`. |
| `--force` | off | Re-author even if `generated-skills/<task>/aip-from-*/` already populated. |
| `--limit` | 0 | Cap number of conversions (0 = no limit). Useful for cost-bounded smoke tests. |
| `--yes` / `-y` | off | Skip the 5-second confirm pause. |
| `--author-model` | `claude-opus-4-7` | Opus per AIP guidance; override only for experiments. |

Cost rule of thumb: ~$0.30–1 per conversion (one task × one `--from` side). 16 tasks × `--from both` = ~$10–25.

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

- **Mode 5 (`aip-from-curated`) converts each curated skill in isolation, 1:1.** `_convert_from_curated` loops over every skill dir under the task's `environment/skills/` and makes a *separate* `claude -p` call per skill (`cli.py`), so a task with N human-authored skills always yields exactly N AIP skills with the same names. Each conversion is blind to the others, so the authoring model **cannot consolidate** a fragmented skill set (e.g. earthquake-phase-association's 4 seismology skills stay 4). This is a hard property of the per-skill loop, independent of the conversion prompt or the AIP skill's own guidance. Mode 4 (`aip-from-instruction`) has no such constraint — it gets one call and chooses its own skill count. To allow mode-5 consolidation you'd change the loop to pass all skill dirs into a single call.

