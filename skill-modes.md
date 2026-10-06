# Skill Modes

Runbook for the evaluation conditions defined in the [README](README.md). For background on what each mode is and why, see the README; this doc focuses on how to run each, where the skill lives in the container, where results land, and how to audit them.

## Overview

| Mode | Authored by | Input | Authored when | Trials use |
|---|---|---|---|---|
| `noskill` | — | — | — | nothing |
| `human-curated` | human | task domain expertise (no file) | offline | committed `vendor/skillsbench/tasks/<task>/environment/skills/` |
| `selfgen-skill-creator` | same model as solver | `vendor/skillsbench/tasks/<task>/instruction.md` | per trial (in-sandbox) | freshly-generated skill (sandbox-local, ephemeral) |
| `aip-from-instruction` | Opus | `vendor/skillsbench/tasks/<task>/instruction.md` | once, locked | committed `generated-skills/<task>/aip-from-instruction/` mounted as skills |
| `aip-spec` | Opus | the task's curated skills + Dockerfile | once, locked | committed `generated-skills/<task>/aip-from-curated/<skill>/` mounted as a skill, plus the `aip-spec` memory file |
| `aip-runtime` | Opus | same pack as `aip-spec` | once, locked | the same pack published to an in-container `aip server`; only the generic `aip-runtime` skill mounted; the `aip-runtime` memory file |
| `model-dist` | — | — | — | not implemented (exits 2); see `prompts/modes-plan.md` Appendix A |

`aip-from-curated` is accepted as a deprecated alias of `aip-runtime`: `eval` prints a note and proceeds as `aip-runtime`. It remains the pack directory name.

Every mode runs the same solver call shape: `aip-skillbench eval --task <T> --model <M> --mode <name>`. The differences are the skill artifacts mounted into the container, what else the container is given, and when/by-whom the skills were authored.

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

## `aip-from-instruction`

Opus authors an AIP skill **once** from `instruction.md` alone, locked, committed; every trial mounts the same skill. Authoring runs offline on the host via `claude -p`; no Docker, no env access during authoring.

Two commands — author once, eval many:

```bash
uv run aip-skillbench convert --task 3d-scan-calc --from instruction
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-instruction
```

Output (committed to git): `generated-skills/<task>/aip-from-instruction/<skill-name>/`.

Notable difference from the curated-side pack: the skill is authored from scratch, so Opus picks its own `<skill-name>` (e.g. `stl-mass-from-scan` for 3d-scan-calc, not the curated `mesh-analysis`), and any helper scripts are written by Opus rather than copied from a human-authored skill.

### Reference run

First validated trial:

- Task: `3d-scan-calc`
- Model: `claude-haiku-4-5`
- Agent: `claude-agent-acp`
- Trial: `3d-scan-calc__fdaf7b47` (run `2026-05-26__17-44-58`)
- Authored skill: `stl-mass-from-scan` (Opus-chosen name; includes its own stdlib-only `scripts/compute_mass.py` and a `references/binary_stl_format.md` explainer)
- Reward: **1.0** (pass)
- Tool calls: 9 (`Skill` launch → `Read` density table → `Terminal` STL size sanity-check → `Terminal` run `compute_mass.py --verbose` → `Read` the script → `Read` density again → …)
- Wall clock: 84.4 s (env 6.1 + agent setup 0.6 + agent execution 60.0 + verifier 2.5)
- Skill activated via `Skill` tool: yes — `Launching skill: stl-mass-from-scan`

Comparison to the old `aip-from-curated` reference run on the same (task, model): both pass; this one used 9 tool calls vs 4, primarily because the Opus-authored skill ships a runnable script that the agent invoked directly and then sanity-checked, rather than writing its own glue code.

---

## The curated-side AIP pack (shared by `aip-spec` and `aip-runtime`)

Opus compiles all of a task's curated skills into **one** AIP procedure (`convert --from curated --single`, the default for these modes): the verbatim 0.5a1 runtime block plus a schema-validated YAML procedure, `metadata.aip-version` frontmatter, the originals preserved under `source/`, and supporting scripts reproduced or adapted. Locked, committed, and gated by `aip-spec validate` (a `runtime_block_outdated` warning counts as a failure, so no campaign mixes block versions). Both modes use the same pack bytes.

```bash
# Author once (one Opus call, ~$0.30-1, ~1-2 min)
uv run aip-skillbench convert --task 3d-scan-calc --from curated --single
```

Authoring is sandboxed: the session sees only the curated skills and Dockerfile under a throwaway `./inputs/`, and its transcript is audited for any access outside the workspace (see README "Sandboxed authoring"); the record lives in `generated-skills/<task>/_authoring/`.

Host layout (committed):

```
generated-skills/3d-scan-calc/
├── aip-from-curated/                  # the pack dir: skill folders only
│   └── stl-mass-calc/
│       ├── SKILL.md                   # frontmatter + runtime block + fenced YAML procedure
│       ├── scripts/…                  # execution-step scripts
│       └── source/…                   # the curated originals
└── _authoring/curated/single/         # prompt, transcript, audit.json, meta.json
```

`eval` validates the pack before every AIP trial and `run-matrix` validates every pack before a campaign spends money.

### Memory files

Both AIP modes get a short, directive `~/.claude/CLAUDE.md` (written to `/root/.claude/CLAUDE.md` before the sandbox user exists; benchflow copies it into `/home/agent/.claude/`). The two texts live side by side in `aip_skillbench/_benchflow_patch.py` (`NUDGE_MEMORY`) and are held constant across campaigns. `human-curated` gets none. `--no-aip-nudge` (or `aip_nudge: false` in a `run-matrix` config) is the explicit ablation. The patch logs `aip memory (<mode>) written` and `timing.json` carries `memory_file` (seconds).

### Decision steps

The decision model (TypeSafe) is off in every mode: decision steps pause and the solver answers them. `--decision-model` is accepted only with `aip-runtime`, where it puts `TYPESAFE_API_KEY` from `.env` into the **server** process's environment (via `AIP_SKILLBENCH_SERVER_ENV`), never the agent's. `eval` refuses it for any other mode; `run-matrix` passes it to `aip-runtime` cells only.

---

## `aip-spec`

The Spec alone. The pack is mounted as a skill; its 0.5a1 runtime block tells the solver to execute the graph itself (start step, each execution step's script with the JSON state on stdin, follow `inputs_to` and routers, answer decisions). No `aip` CLI, no server.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-spec
```

What `eval` sets: `--skills-dir generated-skills/<task>/aip-from-curated`, and `AIP_SKILLBENCH_NUDGE=aip-spec` (unless `--no-aip-nudge`).

Container paths:

| Container path | Origin | Used by agent? |
|---|---|---|
| `/home/agent/.claude/skills/<skill>/` | symlink to benchflow's `--skills-dir` upload | **yes** — the procedure the solver executes |
| `/home/agent/.claude/CLAUDE.md` | the `aip-spec` memory file | yes, loaded as user memory |
| `/app/skills/<curated-skill>/` | benchflow's task-fixtures upload of the curated originals | no — unused in this mode |

Scripts run as the solver (the `agent` sandbox user).

Audit signals (`TRIAL=$(ls -dt jobs/<task>-aip-spec-<model>/*/<task>__* | head -1)`):

```bash
grep '"Launching skill' $TRIAL/agent/acp_trajectory.jsonl          # the pack's skill name
grep -c '"aip ' $TRIAL/agent/acp_trajectory.jsonl                 # 0: no aip CLI in this mode
grep -o 'currentState' $TRIAL/agent/acp_trajectory.jsonl | wc -l  # scripts fed JSON state on stdin
python3 -c "import json; t=json.load(open('$TRIAL/timing.json')); print(sorted(t))"   # no aip_* keys
```

---

## `aip-runtime`

The Protocol. Nothing task-specific is mounted. Before the agent is installed, the benchflow patch (as root) installs the `aip-spec` and `aip` wheels from `build/aip/` into `/opt/aip`, starts `aip server` (filesystem backend) on `127.0.0.1:8000`, and publishes the pack to it. The solver gets only the generic `aip-runtime` skill and `AIP_SERVER`, and is expected to `aip search` with the task's words, `aip info` the match, `aip run <name> --input start.json`, and answer each pause with `aip resume`.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-runtime
```

What `eval` sets: `--skills-dir build/aip-runtime-skill` (only `aip-runtime/SKILL.md`), `--agent-env AIP_SERVER=http://127.0.0.1:8000`, and for the patch `AIP_SKILLBENCH_WHEELS`, `AIP_SKILLBENCH_SERVER=1`, `AIP_SKILLBENCH_PUBLISH=<the one skill folder>`, `AIP_SKILLBENCH_NUDGE=aip-runtime` (unless `--no-aip-nudge`). The pack dir must hold exactly one skill folder (`--single`); `eval` refuses otherwise.

Container paths:

| Container path | Origin | Used by agent? |
|---|---|---|
| `/home/agent/.claude/skills/aip-runtime/` | `build/aip-runtime-skill/` (from `aip runtime --skill`) | **yes** — the protocol directions |
| `/home/agent/.claude/CLAUDE.md` | the `aip-runtime` memory file | yes, loaded as user memory |
| `/opt/aip/` | venv with `aip` and `aip-spec`; `/usr/local/bin/aip` symlinks into it | yes, via the CLI |
| `/opt/aip/packs/<skill>/` | the published pack's upload | no — the server runs it |
| `/opt/aip/catalog/` | the server's filesystem backend | no |
| `/var/log/aip-server.log` | server log | no (useful when debugging) |
| `/app/skills/<curated-skill>/` | benchflow's task-fixtures upload of the curated originals | no — unused in this mode |

**Root vs agent.** The server is a root process, so execution-step scripts run as root in this mode, while in `aip-spec` they run as the solver. That is acceptable for these tasks: outputs land under `/root/`, which the verifier reads.

Audit signals (`TRIAL=$(ls -dt jobs/<task>-aip-runtime-<model>/*/<task>__* | head -1)`):

```bash
grep '"Launching skill' $TRIAL/agent/acp_trajectory.jsonl                 # aip-runtime, not a task skill
grep -o 'aip \(search\|info\|run\|resume\)[^"\\]*' $TRIAL/agent/acp_trajectory.jsonl | head
python3 -c "import json; t=json.load(open('$TRIAL/timing.json')); print({k: t[k] for k in t if k.startswith('aip_')})"
# → aip_install, aip_server, aip_publish
```

`aip run` should name the procedure (`aip run stl-mass-calc …`), not a folder path. No `aip run` in the trajectory means the solver solved the task some other way; report it as such. The `name@revision` the patch published is in benchflow's log.

---

## `model-dist`

Placeholder for the "compile to code without the Spec" ablation. `eval --mode model-dist` exits 2 with "not implemented; see prompts/modes-plan.md Appendix A", and `run-matrix` refuses it up front.

---

## Where the results are

Each `eval` call writes one trial dir:

```
jobs/<task>-<mode>-<model>/
└── <timestamp>/                       # one launch
    └── <task>__<8-hex>/               # one trial
        ├── result.json                # rewards, timing, n_tool_calls, model, scenes
        ├── timing.json                # environment_setup, aip_* (aip-runtime), memory_file, agent_*, verifier
        ├── config.json                # full run config snapshot
        ├── agent/acp_trajectory.jsonl # full agent transcript (one event per line)
        └── verifier/reward.txt        # final 0.0–1.0 score
```

```bash
uv run aip-skillbench reward jobs/3d-scan-calc-aip-runtime-claude-haiku-4-5/<timestamp>/
```
