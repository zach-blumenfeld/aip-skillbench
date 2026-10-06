# aip-skillbench

This repo extends [SkillsBench](https://www.skillsbench.ai) ([repo](https://github.com/benchflow-ai/skillsbench), [paper](https://www.skillsbench.ai/skillsbench.pdf)) to evaluate [AIP-formatted skills](https://github.com/zach-blumenfeld/aip).

## Paper & evaluation data

Raw run data for our papers are published as HuggingFace datasets. Each dataset's card explains the runs and links the exact repo tag to check out the AIP-compiled skills used; the analysis itself is in the paper.

| Paper | Evaluation data                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
|---|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **AIP: A Graph Representation for Learning and Governing Agent Skills** | **For the paper:** [24-task stratified core](https://huggingface.co/datasets/neo4j/aip-skillbench-24task-sonnet-aipv0_3a3) (`aipv0.3a3`) · [3-task medium reference set](https://huggingface.co/datasets/neo4j/aip-skillbench-3med-sonnet-aipv0_3a2) (`aipv0.3a2`).<br>**Additionally**, the earlier (`aipv0.3a2`) [16-task stratified run](https://huggingface.co/datasets/neo4j/aip-skillbench-cohort-ab-sonnet-aipv0_3a2) that drove version bump and surfaced AIP agent self-improvement potential. |


## Overview
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
├── build/aip/                     # aip + aip-spec wheels built by `bootstrap`, installed into trial containers (gitignored)
├── build/skills/                  # `aip skill install` output: aip/ (authoring) and aip-runtime/ (gitignored)
├── build/aip-runtime-skill/       # only aip-runtime/SKILL.md, mounted in aip-runtime trials (gitignored)
└── .claude/skills-src/            # aip and aip-spec clones made by `bootstrap` (gitignored)
```

`generated-skills/AIP_REF.json` records the remote, ref, and commit of both `aip` and `aip-spec`, and the format version, the cohort was authored against; `bootstrap` writes it and it is committed with the cohort.

`vendor/` and `.claude/` are read-only — never write into them. Mode 4 & 5 conversion artifacts go to `generated-skills/<task>/aip-from-{instruction,curated}/<skill>/`.

## Quickstart

```bash
git clone --recurse-submodules git@github.com:zach-blumenfeld/aip-skillbench.git
cd aip-skillbench
uv sync
aip-skillbench bootstrap            # clones aip (aip-0.5a0) and aip-spec (v0.5a1, format 0.5a1)
                                    # into ./.claude/skills-src/, installs the host `aip` and
                                    # `aip-spec` CLIs, builds build/aip/*.whl, writes
                                    # build/skills/ and build/aip-runtime-skill/, and
                                    # records both pins in generated-skills/AIP_REF.json
cp .env.example .env                # fill in ANTHROPIC_API_KEY
aip-skillbench --help
```

To update AIP later: `aip-skillbench bootstrap --force [--aip-ref <branch|tag>] [--aip-sha <commit>] [--aip-spec-ref <tag>]`.
`aip-0.5a0` is a branch, so `--aip-sha <aip.sha from generated-skills/AIP_REF.json>` reproduces
an exact cohort after it has moved. Pack validation (`aip-spec validate`) treats the
`runtime_block_outdated` warning as a failure, so no campaign mixes runtime-block versions.

### AIP 0.5a1 modes

Two AIP modes use the same pack bytes. In `aip-spec` the pack is mounted as a skill and
its 0.5a1 runtime block tells the solver to execute the graph itself. In `aip-runtime`
nothing task-specific is mounted: before the agent starts, the benchflow patch
(`aip_skillbench/_benchflow_patch.py`, driven by env vars `eval` sets) installs the
`aip-spec` and `aip` wheels from `build/aip/` into a venv at `/opt/aip` (`--no-deps`,
runtime dependencies by name from PyPI, since many task images have no git), starts
`aip server` on `127.0.0.1:8000` detached from the setup shell, and publishes the pack
to it with `aip publish`. The solver then finds the procedure with `aip search` and
runs it with `aip run <name>`. `timing.json` records `aip_install`, `aip_server`, and
`aip_publish`; any setup failure fails the trial rather than silently changing the
condition. Scripts run by the server run as root; in `aip-spec` they run as the
solver. Decision steps are answered by the solver at each pause; `--decision-model`
(`aip-runtime` only) would give the server a `TYPESAFE_API_KEY`. `--aip-nudge` seeds a
`~/.claude/CLAUDE.md` memory in the sandbox (`run-matrix` config key `aip_nudge`).
All of these are experimental conditions: record them with the run.

`eval` and `run-matrix` refuse packs that do not validate against the bootstrapped
AIP format, so a cohort authored against an older format must be regenerated
(`convert --force`) after a bump.

### Sandboxed authoring

`convert` runs the authoring session in a throwaway workspace under `build/authoring/`
that contains only the aip skill, `./inputs/` (the curated skills and the task
Dockerfile, or `instruction.md`), and an empty `./out/`. No `--add-dir` is granted and
the prompt names only workspace-relative paths, so the task's `tests/` and
`solution/` are not in view. The session still runs with permissions skipped (it has
to execute `aip` and the scripts it writes), so enforcement is by audit: the full
stream-json transcript is scanned and any tool call whose path fields reach outside
the workspace (or mention `vendor/skillsbench`, `tests/`, `solution/`) fails the
conversion. Prompt, transcript, `audit.json`, and `meta.json` (model, cost, aip
commit) are kept in `generated-skills/<task>/_authoring/<from>/<label>/`, a sibling of
the mounted pack dir, so trials never see them and reviewers can check what the
author read.

## Commands

```bash
# Modes 1, 2, 3 — single command each.
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode noskill
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode human-curated
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-skill-creator

# Modes 4 & 5 — author once (Opus, committed), then eval any model.
aip-skillbench convert --task 3d-scan-calc --from instruction
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-instruction

aip-skillbench convert --task 3d-scan-calc --from curated            # one AIP skill per curated skill
aip-skillbench convert --task 3d-scan-calc --from curated --single   # all curated skills -> one procedure
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-curated
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-curated --decision-model

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
| `--single` | off | Curated side: compile all of a task's curated skills into one AIP procedure instead of one per skill. |

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

- **Token usage is not captured.** benchflow and the `claude-agent-acp` harness don't persist token counts; `result.json` records only `n_tool_calls`, `n_prompts`, and `timing`. So the per-cell "effort" proxies are tool calls and wall clock — not tokens or dollar cost. Aggregate tokens can be read after the fact from the Anthropic Console / Usage API by model + run time-window (since both eval and authoring bill the `.env` key), but not per `(task, mode, trial)`. **Future:** true per-cell token/cost accounting — which would let us compare modes on token efficiency, not just wall clock (e.g. confirm whether `aip-from-curated` is genuinely cheaper than `human-curated`, not just faster) — needs either a logging proxy via `ANTHROPIC_BASE_URL` or a benchflow patch to surface usage from the ACP model-response events into `result.json`.

