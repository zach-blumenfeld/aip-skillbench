# AIP version and ablation benchmark

Spec for the next campaign, decided 2026-10-20. Five scenarios on one 28-task cohort, one
solver, 5 trials per cell: 700 cells. The question is what each layer adds: agent authoring
without graph structure, the paper's AIP format, the current AIP format, and the current
runtime.

## The five scenarios

| scenario | skill bytes | mounted in the container | memory nudge |
|---|---|---|---|
| `human` | the task's curated skills, as shipped | the curated skills dir | none |
| `dist` | compiled with the distillation meta-skill ([/distillation](../distillation)): components and scripts, no graph, no AIP | the pack, as a skill | none |
| `aip-v03` | compiled with the AIP 0.3a3 authoring skill (the format the paper used) | the pack, as a skill | none |
| `aip-spec` | compiled with the AIP 0.6a1 authoring skill | the pack, as a skill | none |
| `aip-rt` | the same 0.6a1 pack bytes as `aip-spec` | only the generic `aip-runtime` skill; the pack is published to an in-container `aip server` | the aip-runtime memory file |

Decisions behind the table:

- `aip-v03`, `aip-spec`, and `dist` all run as a mounted skill with no `aip` CLI in the
  container, the way the paper ran its AIP condition. Mechanically they are the same mode
  with a different pack; the harness exposes that as one `skill` mode that takes a variant.
- The memory file ("your first action is ...") was introduced for `aip-runtime`, where
  nothing task-specific is mounted and two of five cells in the first campaign-1 run never
  touched the protocol. `aip-spec` got it only for symmetry with runtime and passed 5/5
  before and after. In this experiment the mounted-skill scenarios are compared with each
  other, so none of them gets a memory file; the skill's own description does the
  activation. `aip-rt` keeps its nudge and the write-up says so.
- `aip-spec` and `aip-rt` share pack bytes, so the pair isolates the runtime.

## Compilation

Three compilations per task ("variants"), each a recipe of authoring skill plus toolchain,
coexisting in the repo:

| variant | authoring skill | validation gate | pack dir |
|---|---|---|---|
| `dist` | `distillation/SKILL.md` | Agent Skills frontmatter, `name` equals the folder, `source/` present, every referenced file exists, and no AIP runtime block or fenced YAML procedure | `generated-skills/<task>/dist/` |
| `aip-0.3a3` | the aip repo at tag `v0.3a3` (the repo was the skill then: SKILL.md, schemas, `scripts/validate.py`) | that validator | `generated-skills/<task>/aip-0.3a3/` |
| `aip-0.6a1` | the aip-spec authoring skill at `v0.6a1`, aip at `v0.6a1` | `aip-spec validate` plus the functional test with `aip run` | `generated-skills/<task>/aip-0.6a1/` |

Each variant has its own toolchain under `build/<variant>/` and its own pin record; the
single `AIP_REF.json` goes away. Authoring records stay beside the packs under
`_authoring/<variant>/`. A campaign config names scenarios as (mode, variant) pairs.

Compile conditions, identical across the three variants:

- **Author model**: Claude Opus 5.5. One `claude -p` session per task per variant, in the
  sandboxed workspace with the transcript audit, as today.
- **One pack per task** (`--single`): all of a task's curated skills compile into one skill.
  This holds for `aip-0.3a3` too, so `aip-v03` is "the 0.3a3 format under this
  experiment's compile conditions", not a replica of the paper's per-skill compile. The
  paper's numbers are not comparable to this run's and were on older models anyway.
- **Inputs the author sees**: the curated skills, the Dockerfile, the task's
  `instruction.md` (new; curated-side compiles never staged it before), and the full
  environment inputs (`stage_data: full`, the 2026-10-06 decision). This matches what the
  human skill authors had. `sample` (first 2 KB per file) stays available as a one-flag
  stricter rerun if instance tuning is questioned.
- **Never visible**: `tests/`, `solution/`, the verifier, `task.toml`, anything under
  `vendor/skillsbench`. The audit fails the compile on any tool call that touches them.
- The `dist` compile needs a non-interactive wrapper: the distillation skill asks the user
  to name the skill, to confirm installing, and spawns fresh agents to test. The prompt tells
  it to name the skill itself, never ask, test by itself, and write to the output folder.
- The 0.6a1 checklist prompt was written for 0.6a0; re-read it against the 0.6a1 skill
  (type agreement in the validator) before compiling.

Cost: 28 tasks x 3 variants at $2-4 and 10-15 min each, concurrency 5: roughly $170-340
and a few hours. Commit the packs, records, and pins before the campaign.

## The cohort: 28 tasks, four swaps

Start from `configs/campaign-27.yaml` (28 tasks). Strata are the paper's cells: skill
structure (prose-only, mixed, script-heavy) x implementation weight (light, heavy) x
difficulty, with category as a secondary balance. Every swap stays in its difficulty and
category.

| out | why | in | cell of the replacement |
|---|---|---|---|
| fix-build-google-auto | image ships Python 3.9; the aip client needs 3.10, so every runtime cell errored | fix-build-agentops (fallback gh-repo-analytics if its bugswarm image has the same Python) | easy, prose-only, light, software-engineering |
| suricata-custom-exfil | same Python 3.9 problem | software-dependency-audit | medium, prose-only, light, cybersecurity |
| civ6-adjacency-optimizer | 0/5 in every mode of every run (four runs, three models, both AIP generations); task defect, the output dir is root-owned | exam-block-sequencing | hard, prose-only, heavy, mathematics |
| enterprise-information-search | never passed in 35 trials across four models; the instruction's example writes `tokens` as a string and asks for a count the agent cannot know, the verifier requires a number; the answer sets are also missed | jpg-ocr-stat (fallback taxonomy-tree-merge) | hard, mixed, light, office-white-collar |

Replacing beats fixing the Python 3.9 install because a bootstrap-Python patch would make
the runtime container differ from the other four scenarios on exactly those tasks.

Checked and kept: `court-form-filling` (13/15 Haiku 5.5 cells fail one of 47 checks, the
solver fills the court-info box the instruction says to leave empty; Sonnet passed) and
`bike-rebalance` (13/15 fail only the optimality test, 0.8% above a SCIP benchmark;
Sonnet and GPT-5.4 cleared it). Both measure solver and skill quality, not defects.

Structure counts after the swaps: 13 prose-only, 10 mixed, 5 script-heavy (from 12, 10, 6).
Difficulty 5 easy, 13 medium, 10 hard and the category counts are unchanged.

## Solver

- Claude Haiku 5.5, extended thinking off (`--agent-env MAX_THINKING_TOKENS=0`, recorded
  in `campaign.json`).
- No decision model (no Typesafe key): decision steps pause and the solver answers. Only
  `aip-rt` has decisions to resolve.
- The task's `instruction.md` is the solver's prompt in every scenario, as it always was.
- 5 trials per cell, concurrency 10, docker sandbox, `claude-agent-acp`.
- 700 cells, roughly $120 and 10-12 hours; run on the GCP box under tmux, resume across
  days.

## Execution order

1. Variant refactor in the harness: per-variant toolchain and pins, pack dirs and gates,
   the `skill` mode with a variant and optional nudge, the dist wrapper and gate, the 0.3a3
   bootstrap, instruction staging, the 0.6a1 prompt check.
2. Cohort config for the new 28 and the campaign scripts; first image builds for the four
   replacements, which settles the agentops and jpg-ocr-stat questions.
3. Plumbing trial: one task through all five scenarios, one trial each.
4. Compile 28 x 3 with Opus 5.5; commit.
5. Campaign; report.

Standing rules from [campaigns.md](campaigns.md) apply: never edit, tune, or recompile a
pack to make a trial pass; a pack that runs cleanly and computes a wrong answer is a result.
