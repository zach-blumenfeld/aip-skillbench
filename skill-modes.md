# Skill Modes

Runbook for the five evaluation conditions defined in the [README](README.md). For background on what each mode is and why, see the README; this doc focuses on how to run each, where the skill lives in the container, where results land, and how to audit them.

## Overview

| Mode | Authored by | Input | Authored when | Trials use |
|---|---|---|---|---|
| 1 noskill | — | — | — | nothing |
| 2 human-curated | human | task domain expertise (no file) | offline | committed `vendor/skillsbench/tasks/<task>/environment/skills/` |
| 3 selfgen-skill-creator | same model as solver | `vendor/skillsbench/tasks/<task>/instruction.md` | per trial (in-sandbox) | freshly-generated skill (sandbox-local, ephemeral) |
| 4 aip-from-instruction | Opus 4.7 | `vendor/skillsbench/tasks/<task>/instruction.md` | once, locked | committed `generated-skills/<task>/aip-from-instruction/` |
| 5 aip-from-curated | Opus 4.7 | `vendor/skillsbench/tasks/<task>/instruction.md` + `vendor/skillsbench/tasks/<task>/environment/skills/` | once, locked | committed `generated-skills/<task>/aip-from-curated/` |

Every mode runs the same solver call shape: `aip-skillbench eval --task <T> --model <M> --mode <name>`. The differences are the skill artifacts mounted into the container and when/by-whom they were authored.

## Validation status (3d-scan-calc / claude-haiku-4-5, n=1)

| Mode | Trial | Reward | Tool calls | Wall clock |
|---|---|---|---|---|
| 1 noskill | `3d-scan-calc__0edf4a0a` | 1.0 | 8 | 82.0 s |
| 2 human-curated | `3d-scan-calc__1e05fcb6` | 1.0 | 5 | 51.6 s |
| 3 selfgen-skill-creator | `3d-scan-calc__a2d82ebb` | 1.0 | 14 | 113.8 s |
| 4 aip-from-instruction | `3d-scan-calc__fdaf7b47` | 1.0 | 9 | 84.4 s |
| 5 aip-from-curated | `3d-scan-calc__2e275197` | 1.0 | 4 | 51.7 s |

This task on Haiku is at ceiling — every mode passes. Differentiation will require harder tasks, weaker models, or n>1 per cell.

---

## Mode 1 — `noskill`

Baseline. Agent receives only `instruction.md` and the task's environment fixtures (data files, Dockerfile). No skill mounted.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode noskill
```

### Reference run

- Trial: `3d-scan-calc__0edf4a0a`
- Reward: **1.0**, tool calls: 8, wall clock: 82.0 s
- Skill activated: none (none mounted)

---

## Mode 2 — `human-curated`

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

## Mode 3 — `selfgen-skill-creator`

Paper-style self-gen. Each trial spins up a fresh sandbox; the agent runs a *creator* scene (only `skill-creator` skill mounted, reads `instruction.md`, writes one or more skills under the in-container generated-skills root), then a clean *solver* scene starts and gets only those just-generated skills. Same model authors and solves.

```bash
uv run aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-skill-creator
```

Skill-creator source is pinned: `aip-skillbench eval --mode selfgen-skill-creator` always passes `--skill-creator-dir vendor/skillsbench/.agents/skills/skill-creator` to benchflow, so the same SHA of skill-creator is used regardless of what's in your `~/.claude/skills/`. This makes mode-3 results reproducible across machines. If you ever want to use a different skill-creator (e.g. an experimental version), call `bench eval create` directly with `--skill-creator-dir <path>`. Generated skills land under `jobs/<run>/<trial>/_self_gen/<task>-<hex>/` per trial.

### Reference run

- Trial: `3d-scan-calc__a2d82ebb`
- Skill-creator source: `vendor/skillsbench/.agents/skills/skill-creator/`
- Reward: **1.0**, tool calls: 14 (creator scene + solver scene combined), wall clock: 113.8 s
- Note: this is the only mode where authoring happens in-trial — the higher tool-call count and longer wall clock reflect the creator-then-solver two-scene flow inside one sandbox.

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
