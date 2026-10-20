# Skill Modes

Runbook for the evaluation conditions defined in the [README](README.md). For background on what each mode is and why, see the README; this doc focuses on how to run each, where the skill lives in the container, where results land, and how to audit them.

## Overview

| Mode | Authored by | Input | Authored when | Trials use |
|---|---|---|---|---|
| `noskill` | — | — | — | nothing |
| `human-curated` | human | task domain expertise (no file) | offline | committed `vendor/skillsbench/tasks/<task>/environment/skills/` |
| `selfgen-skill-creator` | same model as solver | `vendor/skillsbench/tasks/<task>/instruction.md` | per trial (in-sandbox) | freshly-generated skill (sandbox-local, ephemeral) |
| `skill --variant V` | Opus, under variant V's authoring skill | the task's curated skills, `instruction.md`, Dockerfile, environment inputs | once, locked | committed `generated-skills/<task>/V/<skill>/` mounted as a skill; `--nudge` adds a memory file (off by default) |
| `aip-runtime --variant V` | Opus, under V (`aip-0.6a1`) | same pack as `skill --variant V` | once, locked | the pack published to an in-container `aip server`; only the generic `aip-runtime` skill mounted; the `aip-runtime` memory file (on by default) |

Variants (`aip_skillbench/_variants.py`): `dist` (the distillation meta-skill: a plain
Agent Skill, no AIP), `aip-0.3a3` (the paper's AIP format), `aip-0.6a1` (the current AIP
format; the only one with a runtime). The modes `aip-spec`, `aip-from-instruction`,
`aip-from-curated`, and `model-dist` were removed on 2026-10-20: `aip-spec` is `skill
--variant aip-0.6a1`, and campaign configs name scenarios (`{name, mode, variant, nudge}`)
rather than modes, see [docs/campaigns.md](docs/campaigns.md).

Every mode runs the same solver call shape: `aip-skillbench eval --task <T> --model <M> --mode <name> [--variant V]`. The differences are the skill artifacts mounted into the container, what else the container is given, and when/by-whom the skills were authored.

## Validation status (3d-scan-calc / claude-haiku-4-5, n=1, AIP 0.3-era packs)

| Mode | Trial | Reward | Tool calls | Wall clock |
|---|---|---|---|---|
| noskill | `3d-scan-calc__0edf4a0a` | 1.0 | 8 | 82.0 s |
| human-curated | `3d-scan-calc__1e05fcb6` | 1.0 | 5 | 51.6 s |
| selfgen-skill-creator | `3d-scan-calc__a2d82ebb` | 1.0 | 14 | 113.8 s |
| aip-from-instruction | `3d-scan-calc__fdaf7b47` | 1.0 | 9 | 84.4 s |
| aip-from-curated (old mode 5: pack mounted, `aip` CLI installed) | `3d-scan-calc__2e275197` | 1.0 | 4 | 51.7 s |

These predate the `aip-spec` / `aip-runtime` split. This task on Haiku is at ceiling — every mode passes. Differentiation will require harder tasks, weaker models, or n>1 per cell.

---

## `noskill`

Baseline. Agent receives only `instruction.md` and the task's environment fixtures (data files, Dockerfile). No skill mounted.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode noskill
```

### Reference run

- Trial: `3d-scan-calc__0edf4a0a`
- Reward: **1.0**, tool calls: 8, wall clock: 82.0 s
- Skill activated: none (none mounted)

---

## `human-curated`

Mounts the human-authored skill that ships with the task. This is what the SkillsBench paper calls the "With Skills" condition.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode human-curated
```

Skill location (host, read-only): `vendor/skillsbench/tasks/<task>/environment/skills/<skill-name>/`.

### Reference run

- Trial: `3d-scan-calc__1e05fcb6`
- Skill mounted: `mesh-analysis` (the task's human-authored skill)
- Reward: **1.0**, tool calls: 5, wall clock: 51.6 s
- Skill activated via `Skill` tool: yes — `Launching skill: mesh-analysis`

---

## `selfgen-skill-creator`

Paper-style self-gen. Each trial spins up a fresh sandbox; the agent runs a *creator* scene (only `skill-creator` skill mounted, reads `instruction.md`, writes one or more skills under the in-container generated-skills root), then a clean *solver* scene starts and gets only those just-generated skills. Same model authors and solves.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-skill-creator
```

Skill-creator source is pinned: `aip-skillbench eval --mode selfgen-skill-creator` always passes `--skill-creator-dir vendor/skillsbench/.agents/skills/skill-creator` to benchflow, so the same SHA of skill-creator is used regardless of what's in your `~/.claude/skills/`. This makes self-gen results reproducible across machines. If you ever want to use a different skill-creator (e.g. an experimental version), call `bench eval create` directly with `--skill-creator-dir <path>`. Generated skills land under `jobs/<run>/<trial>/_self_gen/<task>-<hex>/` per trial.

### Reference run

- Trial: `3d-scan-calc__a2d82ebb`
- Skill-creator source: `vendor/skillsbench/.agents/skills/skill-creator/`
- Reward: **1.0**, tool calls: 14 (creator scene + solver scene combined), wall clock: 113.8 s
- Note: this is the only mode where authoring happens in-trial — the higher tool-call count and longer wall clock reflect the creator-then-solver two-scene flow inside one sandbox.

---

## The compiled pack (shared by `skill` and `aip-runtime`)

Opus compiles all of a task's curated skills into **one** pack per variant
(`convert --task T --variant V`): the originals preserved under `source/` with a
`source/README.md` drop log, supporting scripts reproduced or adapted, and a `SKILL.md`
in the variant's format (`dist`: a plain Agent Skill of components; `aip-0.3a3`: a
schema-validated YAML body; `aip-0.6a1`: the verbatim runtime block plus a typed YAML
procedure with `metadata.aip-version`). Locked, committed, and gated by the variant's
validator (`aip-spec validate` for `aip-0.6a1`, strict on `runtime_block_outdated`; the
0.3a3 skill's `scripts/validate.py`; the harness's own `dist_gate`). `skill` and
`aip-runtime` on the same variant use the same pack bytes.

```bash
# Author once per variant (one Opus call, ~$4, ~10-15 min)
uv run aip-skillbench convert --task 3d-scan-calc --variant aip-0.6a1
```

Authoring is sandboxed: the session sees only the curated skills, `instruction.md`, the
Dockerfile, and the environment inputs under a throwaway `./inputs/`, and its transcript
is audited for any access outside the workspace (see README "Sandboxed authoring"); the
record lives in `generated-skills/<task>/_authoring/<variant>/single/`.

Host layout (committed):

```
generated-skills/3d-scan-calc/
├── aip-0.6a1/                         # the pack dir for one variant: skill folders only
│   └── stl-mass-calc/
│       ├── SKILL.md                   # frontmatter + runtime block + fenced YAML procedure
│       ├── scripts/…                  # execution-step scripts
│       └── source/…                   # the curated originals
├── dist/…  aip-0.3a3/…                # the other variants' packs
└── _authoring/aip-0.6a1/single/       # prompt, transcript, audit.json, meta.json
```

`eval` runs the variant's gate before every `skill` / `aip-runtime` trial and
`run-matrix` runs it on every (task, variant) a campaign needs before spending money.

### Memory files

Two texts live side by side in `aip_skillbench/_benchflow_patch.py` (`NUDGE_MEMORY`), written
to `/root/.claude/CLAUDE.md` before the sandbox user exists (benchflow copies it into
`/home/agent/.claude/`) and as `<cwd>/CLAUDE.md`. `aip-runtime` writes its text by default
(nothing task-specific is mounted, so the solver is told to `aip search` first;
`--no-aip-nudge` is the ablation). `skill` writes none by default: the mounted pack is
activated by its own description like any Agent Skill; `--nudge` is the knob. The patch
logs `aip memory (<mode>) written` and `timing.json` carries `memory_file` (seconds).

### Decision steps

The decision model (TypeSafe) is off in every mode: decision steps pause and the solver answers them. `--decision-model` is accepted only with `aip-runtime`, where it puts `TYPESAFE_API_KEY` from `.env` into the **solver's** environment (`--agent-env`): the `aip` client resolves decisions and the server holds no model key (the patch refuses one in `AIP_SKILLBENCH_SERVER_ENV`). benchflow keeps the key out of the trial's `config.json`. `eval` refuses it for any other mode; `run-matrix` passes it to `aip-runtime` cells only.

---

## `skill`

The pack as a skill. Mounted, nothing installed. An AIP pack's runtime block tells the solver to execute the graph itself (start step, each execution step's script with the JSON state on stdin, follow `inputs_to` and routers, answer decisions); a `dist` pack is followed like any skill. No `aip` CLI, no server.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-5-5 --mode skill --variant aip-0.6a1
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-5-5 --mode skill --variant dist
```

What `eval` sets: `--skills-dir generated-skills/<task>/<variant>`, and `AIP_SKILLBENCH_NUDGE=skill` only with `--nudge`.

Container paths:

| Container path | Origin | Used by agent? |
|---|---|---|
| `/home/agent/.claude/skills/<skill>/` | symlink to benchflow's `--skills-dir` upload | **yes** — the skill the solver follows |
| `/home/agent/.claude/CLAUDE.md` | the `skill` memory file, only with `--nudge` | yes, loaded as user memory |
| `/app/skills/<curated-skill>/` | benchflow's task-fixtures upload of the curated originals | no — unused in this mode |

Scripts run as the solver (the `agent` sandbox user).

Audit signals (`TRIAL=$(ls -dt jobs/<task>-skill-<variant>-<model>/*/<task>__* | head -1)`):

```bash
grep '"Launching skill' $TRIAL/agent/acp_trajectory.jsonl          # the pack's skill name
grep -c '"aip ' $TRIAL/agent/acp_trajectory.jsonl                 # 0: no aip CLI in this mode
grep -o '"state"' $TRIAL/agent/acp_trajectory.jsonl | wc -l       # aip-0.6a1: scripts fed JSON state on stdin
python3 -c "import json; t=json.load(open('$TRIAL/timing.json')); print(sorted(t))"   # no aip_* keys; memory_file only with --nudge
```

---

## `aip-runtime`

The Protocol. Nothing task-specific is mounted. Before the agent is installed, the benchflow patch (as root) installs the variant's `aip-spec` and `aip` wheels from `build/<variant>/wheels/` into `/opt/aip`, starts `aip server` (filesystem backend) on `127.0.0.1:8000`, and publishes the pack to it. The solver gets only the generic `aip-runtime` skill and `AIP_SERVER`, and is expected to `aip search` with the task's words, `aip info` the match, `aip run <name> --input start.json`, and answer each pause with `aip resume`.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-5-5 --mode aip-runtime --variant aip-0.6a1
```

What `eval` sets: `--skills-dir build/<variant>/aip-runtime-skill` (only `aip-runtime/SKILL.md`), `--agent-env AIP_SERVER=http://127.0.0.1:8000`, and for the patch `AIP_SKILLBENCH_WHEELS`, `AIP_SKILLBENCH_SERVER=1`, `AIP_SKILLBENCH_PUBLISH=<the one skill folder>`, `AIP_SKILLBENCH_NUDGE=aip-runtime` (unless `--no-aip-nudge`). The pack dir must hold exactly one skill folder; `eval` refuses otherwise, and refuses a variant without a runtime (`dist`, `aip-0.3a3`).

Container paths:

| Container path | Origin | Used by agent? |
|---|---|---|
| `/home/agent/.claude/skills/aip-runtime/` | `build/<variant>/aip-runtime-skill/` (from `aip runtime --skill`) | **yes** — the protocol directions |
| `/home/agent/.claude/CLAUDE.md` | the `aip-runtime` memory file | yes, loaded as user memory |
| `/opt/aip/` | venv with `aip` and `aip-spec`; `/usr/local/bin/aip` symlinks into it | yes, via the CLI |
| `/opt/aip/packs/<skill>/` | the published pack's upload | no — the server serves it |
| `/home/agent/.aip/` | the client's run files and its cache of the revision's `scripts/` and `assets/` | yes, via the CLI |
| `/opt/aip/catalog/` | the server's filesystem backend | no |
| `/var/log/aip-server.log` | server log | no (useful when debugging) |
| `/app/skills/<curated-skill>/` | benchflow's task-fixtures upload of the curated originals | no — unused in this mode |

**Root vs agent.** The server is a root process, but it runs no scripts: the solver's `aip` client runs every execution step as the solver, from its cache, as in `skill` mode. Outputs land under `/root/`, which the verifier reads.

Audit signals (`TRIAL=$(ls -dt jobs/<task>-aip-runtime-<variant>-<model>/*/<task>__* | head -1)`):

```bash
grep '"Launching skill' $TRIAL/agent/acp_trajectory.jsonl                 # aip-runtime, not a task skill
grep -o 'aip \(search\|info\|run\|resume\)[^"\\]*' $TRIAL/agent/acp_trajectory.jsonl | head
python3 -c "import json; t=json.load(open('$TRIAL/timing.json')); print({k: t[k] for k in t if k.startswith('aip_')})"
# → aip_install, aip_server, aip_publish
```

`aip run` should name the procedure (`aip run stl-mass-calc …`), not a folder path. No `aip run` in the trajectory means the solver solved the task some other way; report it as such. The `name@revision` the patch published is in benchflow's log.

---

## Where the results are

Each `eval` call writes one trial dir:

```
jobs/<task>-<mode>[-<variant>]-<model>/
└── <timestamp>/                       # one launch
    └── <task>__<8-hex>/               # one trial
        ├── result.json                # rewards, timing, n_tool_calls, model, scenes
        ├── timing.json                # environment_setup, aip_* (aip-runtime), memory_file, agent_*, verifier
        ├── config.json                # full run config snapshot
        ├── agent/acp_trajectory.jsonl # full agent transcript (one event per line)
        └── verifier/reward.txt        # final 0.0–1.0 score
```

```bash
uv run aip-skillbench reward jobs/3d-scan-calc-aip-runtime-aip-0.6a1-claude-haiku-5-5/<timestamp>/
```
