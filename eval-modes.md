# Eval Modes

This repo extends [SkillsBench](https://www.skillsbench.ai) ([repo](https://github.com/benchflow-ai/skillsbench), [paper](https://www.skillsbench.ai/skillsbench.pdf)). SkillsBench is a containerized benchmark — 84+ tasks across 11 domains, run via the [BenchFlow SDK](https://github.com/benchflow-ai/benchflow) — that measures agent pass rate under three skill conditions: 

1. **no skills** (mode 1), 
2. **human-curated skills** authored offline by domain experts (mode 2). See the paper for the comparative findings across model + harness configurations.
3. **self-generated skills** authored by the same agent at trial time (mode 3).

We add two AIP modes here, both experimental: 
4. **AIP from instruction** (mode 4) and 
5. **AIP from human-curated** (mode 5). 

Both use Opus 4.7 to author once via the [AIP skill](https://github.com/zach-blumenfeld/aip), commit the result, and mount it across all trials — matching AIP's author-once-consume-many design pattern.

Five conditions per (task, model), distinguished by who/what authored the skill an agent has access to during a trial.

## Overview

| Mode | Authored by | Input | Authored when | Trials use |
|---|---|---|---|---|
| 1 noskill | — | — | — | nothing |
| 2 human-curated | human | task domain expertise (no file) | offline | committed `vendor/skillsbench/tasks/<task>/environment/skills/` |
| 3 skill-creator selfgen | same model as solver | `vendor/skillsbench/tasks/<task>/instruction.md` | per trial (in-sandbox) | freshly-generated skill (sandbox-local, ephemeral) |
| 4 aip-from-instruction | Opus 4.7 | `vendor/skillsbench/tasks/<task>/instruction.md` | once, locked | committed `generated-skills/<task>/aip-from-instruction/` |
| 5 aip-from-curated | Opus 4.7 | `vendor/skillsbench/tasks/<task>/instruction.md` + `vendor/skillsbench/tasks/<task>/environment/skills/` | once, locked | committed `generated-skills/<task>/aip-from-curated/` |

Every mode runs the same solver call shape: `aip-skillbench eval --task <T> --model <M> --mode <name>`. The differences are the skill artifacts mounted into the container and when/by-whom they were authored.

---

## Mode 1 — `noskill`

Baseline. Agent receives only `instruction.md` and the task's environment fixtures (data files, Dockerfile). No skill mounted.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode noskill
```

Status: wired, not yet validated end-to-end.

---

## Mode 2 — `human-curated`

Mounts the human-authored skill that ships with the task. This is what the SkillsBench paper calls the "With Skills" condition.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode human-curated
```

Skill location (host, read-only): `vendor/skillsbench/tasks/<task>/environment/skills/<skill-name>/`. Status: wired, not yet validated end-to-end.

---

## Mode 3 — `selfgen-skill-creator`

Paper-style self-gen. Each trial spins up a fresh sandbox; the agent runs a *creator* scene (only `skill-creator` skill mounted, reads `instruction.md`, writes one or more skills under the in-container generated-skills root), then a clean *solver* scene starts and gets only those just-generated skills. Same model authors and solves.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-skill-creator
```

Prereq: `~/.claude/skills/skill-creator/` must exist on the host. Auto-discovered by `_resolve_skill_creator_root` in `benchflow/rollout.py:146-199`. Generated skills land under `jobs/<run>/<trial>/_self_gen/<task>-<hex>/` per trial. Status: wired, not yet validated end-to-end.

---

## Mode 4 — `aip-from-instruction`

Opus 4.7 authors an AIP skill **once** from `instruction.md` alone, locked, committed; every trial mounts the same skill. Authoring runs offline on the host via `claude -p`; no Docker, no env access during authoring.

Two commands — author once, eval many:

```bash
uv run aip-skillbench convert --task 3d-scan-calc --from instruction
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-instruction
```

Output (committed to git): `generated-skills/<task>/aip-from-instruction/<skill-name>/`.

Notable difference from mode 5: the skill is authored from scratch, so Opus picks its own `<skill-name>` (e.g. `stl-mass-from-scan` for 3d-scan-calc, not the curated `mesh-analysis`), and any helper scripts are written by Opus rather than copied from a human-authored skill.

### Reference run

First validated mode-4 trial:

- Task: `3d-scan-calc`
- Model: `claude-haiku-4-5`
- Agent: `claude-agent-acp`
- Trial: `3d-scan-calc__fdaf7b47` (run `2026-05-26__17-44-58`)
- Authored skill: `stl-mass-from-scan` (Opus-chosen name; includes its own stdlib-only `scripts/compute_mass.py` and a `references/binary_stl_format.md` explainer)
- Reward: **1.0** (pass)
- Tool calls: 9 (`Skill` launch → `Read` density table → `Terminal` STL size sanity-check → `Terminal` run `compute_mass.py --verbose` → `Read` the script → `Read` density again → …)
- Wall clock: 84.4 s (env 6.1 + agent setup 0.6 + agent execution 60.0 + verifier 2.5)
- Skill activated via `Skill` tool: yes — `Launching skill: stl-mass-from-scan`

Comparison to mode-5 reference run on the same (task, model): both pass; mode-4 used 9 tool calls vs mode-5's 4, primarily because the Opus-authored skill ships a runnable script that the agent invoked directly and then sanity-checked, rather than writing its own glue code.

---

## Mode 5 — `aip-from-curated`

Opus 4.7 takes the existing human-curated skill and converts it to an AIP-compliant skill: schema-validated YAML body, `metadata.aip.{spec,schemaId}` frontmatter, preserved `name:`, scripts copied verbatim. Locked, committed, mounted into every trial.

### How to run

Two steps. **Author once**, then **eval many** times across models / repeats.

```bash
# Step 1 — convert curated → AIP (one Opus call, ~$0.30-1, ~1-2 min)
uv run aip-skillbench convert --task 3d-scan-calc --from curated

# Step 2 — eval (one trial; ~30-60 s for Haiku on this task)
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode aip-from-curated
```

Defaults: `--author-model claude-opus-4-7` (per AIP spec: largest available frontier model for authoring). The eval `--model` is independent and should be whatever you're measuring.

### Where the skill is

Host (committed in this repo):

```
generated-skills/3d-scan-calc/aip-from-curated/
└── mesh-analysis/
    ├── SKILL.md                       # AIP frontmatter + fenced YAML body
    ├── scripts/mesh_tool.py           # verbatim copy from the curated skill
    └── source/
        ├── ORIGINAL_SKILL.md          # the human-written original, preserved
        └── procedure.schema.json      # AIP schema the YAML body validates against
```

Inside the container, three paths exist after env setup — same skill, three locations:

| Container path | Origin | Used by agent? |
|---|---|---|
| `/skills/mesh-analysis/` | benchflow's runtime upload from `--skills-dir` (`benchflow/agents/install.py:239`) | indirect — symlinked from below |
| `/home/agent/.claude/skills/mesh-analysis/` | symlink, claude-agent-acp's skill-discovery path | **yes** — the agent reads this |
| `/app/skills/mesh-analysis/` | benchflow's task-fixtures upload (`benchflow/rollout.py:544`, copies the original curated skill) | no — unused in this mode |

The sandbox-user default for `bench eval create` is `agent` (so `/home/agent/.claude/skills/…`); pass `--sandbox-user` to override.

### Where the results are

Each call to `aip-skillbench eval --mode aip-from-curated` writes one trial dir:

```
jobs/3d-scan-calc-aip-from-curated-claude-haiku-4-5/
└── <timestamp>/                       # one launch
    └── 3d-scan-calc__<8-hex>/         # one trial
        ├── result.json                # rewards, timing, n_tool_calls, model, scenes
        ├── rewards.jsonl              # terminal reward event(s)
        ├── timing.json                # env_setup + agent_execution + verifier
        ├── config.json                # full run config snapshot
        ├── agent/
        │   ├── acp_trajectory.jsonl   # full agent transcript (one event per line)
        │   ├── claude_agent_acp.txt   # stdout/stderr of the harness process
        │   └── install-stdout.txt
        ├── trajectory/
        │   └── acp_trajectory.jsonl   # mirror of agent/acp_trajectory.jsonl
        ├── verifier/
        │   ├── reward.txt             # final 0.0–1.0 score (one number)
        │   ├── ctrf.json              # Common Test Report Format
        │   └── test-stdout.txt
        └── artifacts/
```

Quick reads:

```bash
# Score
cat jobs/3d-scan-calc-aip-from-curated-claude-haiku-4-5/*/3d-scan-calc__*/verifier/reward.txt

# Full result summary
cat jobs/3d-scan-calc-aip-from-curated-claude-haiku-4-5/*/3d-scan-calc__*/result.json

# Helper
uv run aip-skillbench reward jobs/3d-scan-calc-aip-from-curated-claude-haiku-4-5/<timestamp>/
```

### How to tell the AIP skill was actually used

Three audit signals in the trajectory. Use the latest trial dir:

```bash
TRIAL=$(ls -dt jobs/3d-scan-calc-aip-from-curated-claude-haiku-4-5/*/3d-scan-calc__* | head -1)
```

**1. Skill-tool invocation** — Claude Code emits a `Skill` tool call when a skill activates. Grep for it:

```bash
grep '"Launching skill"' $TRIAL/agent/acp_trajectory.jsonl
# → "text": "Launching skill: mesh-analysis"
```

**2. Container path in agent-written code** — the agent's own code references `~/.claude/skills/<skill>/` paths. Look at any file the agent wrote via the `Write` tool:

```bash
python3 -c "
import json
for line in open('$TRIAL/agent/acp_trajectory.jsonl'):
    e = json.loads(line)
    if e.get('type') == 'tool_call':
        for c in e.get('content', []):
            if c.get('type') == 'diff':
                print(c.get('newText', '')[:500])
"
# Look for: sys.path.insert(0, '/home/agent/.claude/skills/mesh-analysis/scripts')
#                                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                                                   the AIP skill, mounted under .claude/skills/
```

**3. Skill content matches AIP, not the curated original** — diff what's in the container vs the host. The container copy comes from `generated-skills/<task>/aip-from-curated/`, so its `SKILL.md` has the AIP frontmatter (`metadata.aip.spec`, `metadata.aip.schemaId`) and a fenced YAML body. If you see the original markdown-only format in the trajectory, something is wrong:

```bash
head -10 generated-skills/3d-scan-calc/aip-from-curated/mesh-analysis/SKILL.md
# → ---
# → name: mesh-analysis
# → description: …
# → metadata:
# →   aip:
# →     spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
# →     schemaId: …
# → ---
```

### Reference run (sanity check)

First validated mode-5 trial:

- Task: `3d-scan-calc`
- Model: `claude-haiku-4-5`
- Agent: `claude-agent-acp`
- Trial: `3d-scan-calc__2e275197` (run `2026-05-26__17-23-22`)
- Reward: **1.0** (pass)
- Tool calls: 4 (`Skill` launch → `Read` density table → `Write` script → `Terminal` execute)
- Wall clock: 51.7 s (env setup 4.1 + agent setup 0.6 + agent execution 30.0 + verifier 2.5)
- Computed: main part volume 6242.89 cm³, material ID 42 (Unobtanium), mass 34648.04 g

Sets a known-good baseline for the (task, model) pair. Re-running mode-5 on this pair should produce comparable reward and similar tool-call structure.
