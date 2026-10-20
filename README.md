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

**We add compiled-skill conditions here**, all experimental. An Opus author compiles
each task's curated skills once into one pack under a **compile variant** (an authoring
skill plus its toolchain and validation gate), the pack is committed, and every trial
uses the same bytes: the author-once-consume-many pattern. Three variants exist
(`aip_skillbench/_variants.py`):

| Variant | Authoring skill | What the pack is |
|---|---|---|
| `dist` | the distillation meta-skill in [`distillation/`](distillation/) | a plain Agent Skill of components and scripts: no graph, no AIP |
| `aip-0.3a3` | the aip repo at tag `v0.3a3` (the format the AIP paper used) | an AIP skill: a schema-validated YAML body |
| `aip-0.6a1` | the aip-spec authoring skill at `v0.6a1`, with aip `v0.6a1` | an AIP procedure: runtime block plus typed YAML graph; the only variant with a runtime |

The solver **mode** says what the trial container gets:

| Mode | In the trial container | Measures |
|---|---|---|
| `noskill` | nothing | baseline |
| `human-curated` | the task's bundled human-authored skills | the "With Skills" condition |
| `selfgen-skill-creator` | a skill the model writes at trial time (paper-style self-gen) | self-generation |
| `skill --variant V` | V's pack mounted as a skill; nothing installed; `--nudge` (off by default) adds a memory file naming it as the first action | the compiled skill, as a skill: an AIP pack's runtime block has the solver execute the graph itself |
| `aip-runtime --variant V` | only the generic `aip-runtime` skill; V's pack is published to an `aip server` in the container; `AIP_SERVER` set; the `aip-runtime` memory file (on by default) | the Protocol: `aip search` → `aip run <name>` → answer pauses |

A campaign names **scenarios**, `{name, mode, variant?, nudge?}`; the one in
[`configs/campaign-ablation.yaml`](configs/campaign-ablation.yaml) runs five
(`human`, `dist`, `aip-v03`, `aip-spec`, `aip-rt`) on 28 tasks. The design is in
[docs/aip-version-ablation-benchmark.md](docs/aip-version-ablation-benchmark.md).


See [skill-modes.md](skill-modes.md) for the full runbook.

## Layout

```
aip-skillbench/
├── aip_skillbench/                # CLI package (_variants.py: the compile variants)
├── distillation/                  # the `dist` variant's authoring skill (committed)
├── generated-skills/              # packs and authoring records (committed)
│   ├── REFS.json                  #   every variant's pins, written by `bootstrap`
│   └── <task>/<variant>/<skill>/  #   the pack; _authoring/<variant>/single/ beside it
├── jobs/                          # bench run outputs (gitignored)
├── runs/                          # run-matrix campaigns (gitignored)
├── vendor/skillsbench/            # submodule of benchflow-ai/skillsbench (read-only)
└── build/<variant>/               # per variant, made by `bootstrap` (gitignored):
    ├── src/{aip,aip-spec}/        #   clones (aip-0.3a3: aip only; dist: none)
    ├── skill/<name>/              #   the authoring skill copied into every workspace
    ├── wheels/                    #   aip-0.6a1: installed into aip-runtime containers
    ├── aip-runtime-skill/         #   aip-0.6a1: only aip-runtime/SKILL.md
    └── REF.json                   #   refs, shas, format version
```

`generated-skills/REFS.json` records, per variant, the remote, ref, and commit of its
repos (or, for `dist`, this repo's commit) and the format version; `bootstrap` writes it
and it is committed with the packs.

`vendor/` is read-only — never write into it.

## Quickstart

```bash
git clone --recurse-submodules git@github.com:zach-blumenfeld/aip-skillbench.git
cd aip-skillbench
uv sync
aip-skillbench bootstrap            # every variant: clones its repos into build/<variant>/src/,
                                    # copies its authoring skill to build/<variant>/skill/, and
                                    # for aip-0.6a1 installs the host `aip` and `aip-spec` CLIs
                                    # and builds the wheels; records generated-skills/REFS.json
cp .env.example .env                # fill in ANTHROPIC_API_KEY
aip-skillbench --help
```

`bootstrap --variant V --force` rebuilds one variant; `--aip-sha <commit>` pins the aip
clone for an exact reproduction (REFS.json has the shas). The variants' refs are
constants in `aip_skillbench/_variants.py`. Each variant's gate runs from its own clone,
so it does not depend on which `aip-spec` is on PATH; the `aip-0.6a1` gate treats the
`runtime_block_outdated` warning as a failure, so no campaign mixes runtime-block versions.

### The `skill` and `aip-runtime` modes

`skill --variant V` mounts V's pack as a skill and installs nothing. An AIP pack's
runtime block tells the solver to execute the graph itself; a `dist` pack is a plain
skill. The pack is activated by its own description like any Agent Skill; `--nudge`
(off by default) also writes a `~/.claude/CLAUDE.md` naming it as the mandatory first
action, which is the ablation knob.

`aip-runtime --variant V` (V must have a runtime: `aip-0.6a1`) mounts nothing
task-specific: before the agent starts, the benchflow patch
(`aip_skillbench/_benchflow_patch.py`, driven by env vars `eval` sets) installs V's
`aip-spec` and `aip` wheels into a venv at `/opt/aip` (`--no-deps`, runtime
dependencies by name from PyPI, since many task images have no git), starts `aip
server` on `127.0.0.1:8000` detached from the setup shell, and publishes the pack to it
with `aip publish`. The solver then finds the procedure with `aip search` and runs it
with `aip run <name>`. `timing.json` records `aip_install`, `aip_server`, and
`aip_publish`; any setup failure fails the trial rather than silently changing the
condition. The server runs no scripts: the solver's `aip` client runs them as the
solver. Decision steps are answered by the solver at each pause; `--decision-model`
(refused elsewhere) puts `TYPESAFE_API_KEY` in the solver's environment, where the
client resolves decisions; the server never holds a model key. The `aip-runtime`
memory file (`_benchflow_patch.NUDGE_MEMORY`) is on by default because nothing
task-specific is mounted; `--no-aip-nudge` is the ablation. The pack must hold a single
skill folder; `eval` refuses otherwise. All of these are experimental conditions:
record them with the run.

`eval` and `run-matrix` refuse packs that fail their variant's gate, so a cohort
authored against an older format must be regenerated (`convert --force`) after a bump.

### Sandboxed authoring

`convert --variant V` runs the authoring session in a throwaway workspace under
`build/authoring/` that contains only V's authoring skill (`build/V/skill/`), `./inputs/`
(the curated skills, the task's `instruction.md`, the Dockerfile, and the task's
`environment/` input files as they are, so the author can test the compiled skill
against the real inputs the way a human skill author would), an empty `./out/`, and a
`./scratch/` for functional-test inputs (discarded). Never `tests/` or `solution/`.
The prompt (`aip_skillbench/_prompts.py`: one body plus a note per variant kind) tells
the author to name the skill itself, never ask, and never spawn sub-agents, since a
nested session's tool calls are outside the audit.
The author can tune to the instance; that is accepted as part of the "distilled from
curated knowledge" condition and recorded in the pack's `meta.json` (`stage_data`).
`--stage-data sample` (first 2 KB of each file plus a manifest) is the stricter,
format-only condition for experiments. No `--add-dir` is granted and
the prompt names only workspace-relative paths, so the task's `tests/` and
`solution/` are not in view. The session still runs with permissions skipped (it has
to execute `aip-spec validate`, `aip run`, and the scripts it writes), so enforcement is by audit: the full
stream-json transcript is scanned and any tool call whose path fields reach outside
the workspace (or mention `vendor/skillsbench`, `tests/`, `solution/`) fails the
conversion. Prompt, transcript, `audit.json`, and `meta.json` (author model, cost, the
variant's pins) are kept in `generated-skills/<task>/_authoring/<variant>/single/`, a
sibling of the mounted pack dir, so trials never see them and reviewers can check what
the author read.

## Commands

```bash
# Modes 1, 2, 3 — single command each.
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode noskill
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode human-curated
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5 --mode selfgen-skill-creator

# Compiled skills — compile once per variant (Opus, committed), then eval any model.
aip-skillbench convert --task 3d-scan-calc --variant dist        # all curated skills -> one pack
aip-skillbench convert --task 3d-scan-calc --variant aip-0.3a3
aip-skillbench convert --task 3d-scan-calc --variant aip-0.6a1
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-5-5 --mode skill --variant dist
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-5-5 --mode skill --variant aip-0.6a1 --nudge   # memory-file knob
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-5-5 --mode aip-runtime --variant aip-0.6a1
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-5-5 --mode aip-runtime --variant aip-0.6a1 --no-aip-nudge
aip-skillbench eval    --task 3d-scan-calc --model claude-haiku-5-5 --mode aip-runtime --variant aip-0.6a1 --decision-model

# Compile in bulk — parallel claude -p calls, skips packs that exist and pass their gate.
aip-skillbench batch-convert --task 3d-scan-calc --task exoplanet-detection-period \
                             --variant dist --variant aip-0.6a1 --concurrency 4

# Inspect results
aip-skillbench reward jobs/3d-scan-calc-aip-runtime-aip-0.6a1-claude-haiku-5-5/<timestamp>/
```

See [skill-modes.md](skill-modes.md) for each mode's authoring input, container mount paths, audit signals, and reference runs.

To run a campaign over a task collection (compile the collection's packs per variant, run the campaign, read the results), see [docs/campaigns.md](docs/campaigns.md). To sweep many `(task × model × scenario × trial)` combinations concurrently with live progress, see [run-matrix.md](run-matrix.md).

### `batch-convert` flags

| flag | default | notes |
|---|---|---|
| `--task` (repeatable) | — | Task name(s). Required unless `--pattern` is given. |
| `--pattern` | `*` | Glob filter on task names. Ignored if any `--task` is set. |
| `--variant` (repeatable) | every variant | Which compile variant(s) to author under. |
| `--concurrency` / `-j` | 4 | Parallel `claude -p` calls. Real ceiling is the Anthropic per-org rate limit for the author model. |
| `--force` | off | Re-author even if a pack exists and passes its gate. |
| `--limit` | 0 | Cap number of conversions (0 = no limit). Useful for cost-bounded smoke tests. |
| `--yes` / `-y` | off | Skip the 5-second confirm pause. |
| `--author-model` | `claude-opus-5-5` | Opus per AIP guidance; override only for experiments. |
| `--stage-data` | `full` | What the author sees of the task's inputs: `full`, `sample` (first 2 KB per file), or `none`. |

Cost: measured mean $4.19 per pack with Opus 5.5 under the 0.5a1 checklist (28 packs, $2.03 to $7.51); one `claude -p` session of 40 to 100 tool calls each.

## Agents & models

The **solver** (the agent attempting each task during `eval`) can be any agent BenchFlow supports. Pass `--agent` to switch:

```bash
aip-skillbench eval --task 3d-scan-calc --model claude-haiku-4-5    --agent claude-agent-acp   # Anthropic (default)
aip-skillbench eval --task 3d-scan-calc --model gpt-5.2-codex       --agent codex-acp          # OpenAI
aip-skillbench eval --task 3d-scan-calc --model gemini-3-flash-preview --agent gemini          # Google
```

Each agent reads its own API key from `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`). The `--model` string is agent-specific.

## Known limitations

- **Authoring is Anthropic-only.** `aip-skillbench convert` shells out to Claude Code (`claude -p`) and defaults to `claude-opus-5-5` per AIP guidance. Authoring with OpenAI / Google models would require an adapter that mounts the authoring skill in those harnesses' prompt format. Solver evaluation is not restricted — see above.

- **Every compile is curated-side and single.** A pack is always all of a task's curated skills compiled into one skill by one `claude -p` call. The earlier per-skill and instruction-only compiles (`--from instruction`, `--per-skill`) were removed on 2026-10-20 with the variant refactor; the paper's 0.3a3 cohort was compiled per skill, so its packs are not reproducible with this harness.

- **Token usage is not captured.** benchflow and the `claude-agent-acp` harness don't persist token counts; `result.json` records only `n_tool_calls`, `n_prompts`, and `timing`. So the per-cell "effort" proxies are tool calls and wall clock — not tokens or dollar cost. Aggregate tokens can be read after the fact from the Anthropic Console / Usage API by model + run time-window (since both eval and authoring bill the `.env` key), but not per `(task, mode, trial)`. **Future:** true per-cell token/cost accounting — which would let us compare modes on token efficiency, not just wall clock (e.g. confirm whether the AIP modes are genuinely cheaper than `human-curated`, not just faster) — needs either a logging proxy via `ANTHROPIC_BASE_URL` or a benchflow patch to surface usage from the ACP model-response events into `result.json`.

