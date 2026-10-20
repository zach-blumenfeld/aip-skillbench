# Plan: harness changes for the version and ablation benchmark

Implements the spec in [aip-version-ablation-benchmark.md](aip-version-ablation-benchmark.md).
Four steps, in order; each has the files it touches, a proof that is run before it is
called done, and a `Done:` line to fill in with the commit. Compiling the cohort (S5) and
running the campaign (S6) are separate, gated by cost, and not part of this plan.

Conventions (from `prompts/modes-plan.md`): no step is done until its proof ran and its
output is quoted on the `Done:` line; nothing is committed without being asked; nothing
under `skill-analysis/`, `runs/`, `jobs/`, or `build/` is committed.

## Vocabulary

- **variant**: a compile recipe: authoring skill, toolchain refs, validation gate, pack dir
  name. Three: `dist`, `aip-0.3a3`, `aip-0.6a1`. Registry in
  `aip_skillbench/_variants.py`; everything per-variant keys off it.
- **mode**: what the solver's container gets. After this plan: `noskill`, `human-curated`,
  `selfgen-skill-creator`, `skill` (a variant's pack mounted as a skill, optional nudge),
  `aip-runtime` (a variant's pack published to the in-container server, nudge on).
  `aip-spec`, `aip-from-instruction`, `aip-from-curated`, `model-dist` are removed; the
  spec's scenario names live in campaign configs, not in the harness.
- **scenario**: a campaign row: `{name, mode, variant?, nudge?}`. Cells are keyed by
  scenario name; `summary.jsonl` rows carry `scenario`, `mode`, `variant`.

Layout after S1:

    build/<variant>/src/{aip,aip-spec}/   clones (0.3a3 has only aip; dist has none)
    build/<variant>/skill/<name>/         the authoring skill copied into workspaces
    build/<variant>/wheels/               aip-0.6a1 only
    build/<variant>/aip-runtime-skill/    aip-0.6a1 only
    build/<variant>/REF.json              refs, shas, format version, recorded_at
    generated-skills/<task>/<variant>/<skill-name>/      the pack (one per task)
    generated-skills/<task>/_authoring/<variant>/single/ prompt, transcript, audit, meta
    generated-skills/REFS.json            the three REF.json blocks, written by bootstrap,
                                          committed with the packs

The current `generated-skills/<task>/aip-from-*` dirs, `_authoring/{curated,instruction}`,
and `AIP_REF.json` are deleted in S1 (decided 2026-10-20: nothing in them is kept).

## S1. Variants in the harness: registry, bootstrap, gates  [x]

Changes:

- `aip_skillbench/_variants.py` (new): `Variant` dataclass and `VARIANTS`:
  - `aip-0.6a1`: aip `v0.6a1`, aip-spec `v0.6a1`; skill from `aip skill install`; host
    CLIs `aip-spec` and `aip` via `uv tool install --editable` (this is the only variant
    whose authoring needs them on PATH); wheels; runtime skill; gate = `aip-spec validate`
    with `runtime_block_outdated` strict (today's `validate_pack`).
  - `aip-0.3a3`: aip `v0.3a3` only (the repo is the skill: `SKILL.md`, `assets/`,
    `references/`, `scripts/validate.py`); copy it minus `tests/`, `img/`, `.gitignore`;
    gate = `python scripts/validate.py <pack>` from that clone. Check its arguments and
    exit codes when wiring it; record what it checks in the docstring.
  - `dist`: skill from `distillation/` in this repo; no clones; gate = the harness's own
    `dist_gate()`: Agent Skills frontmatter (`name`, `description`), `name` equals the
    folder and is kebab-case under 65 chars, `source/` exists, every relative path
    mentioned in SKILL.md resolves inside the pack, and the body has no AIP runtime block
    heading and no fenced YAML block that parses with a `steps` key.
- `aip_skillbench/_aip.py`: paths take a variant (`src_dir`, `skill_dir`, `wheels`,
  `runtime_skill_dir`, `read_ref`), `validate_packs(variant, pack_root)` dispatches to the
  variant's gate. `AIP_REF_FILE` becomes `REFS_FILE`.
- `cli.py bootstrap --variant <name>` (repeatable; default all three; `--force`;
  `--aip-sha` applies to the named variant). Writes `build/<variant>/REF.json` and merges
  into `generated-skills/REFS.json`.
- `.gitignore`: `build/` already ignored; confirm.
- Delete the old generated-skills dirs and `AIP_REF.json`; `git rm` them so the working
  tree is clean of the 2026-10-19 test compiles.

Proof:

    uv run aip-skillbench bootstrap --force
    ls build/                                   # aip-0.3a3  aip-0.6a1  dist
    cat generated-skills/REFS.json              # three blocks with shas
    aip-spec --version                          # 0.6a1
    ls build/aip-0.6a1/wheels                   # aip_spec-*.whl aip-*.whl
    ls build/aip-0.3a3/skill/aip/scripts        # validate.py validate_schema.py
    ls build/dist/skill                         # distillation (or the skill's name)
    uv run python -c "from aip_skillbench._variants import VARIANTS; print(sorted(VARIANTS))"
    git status --short generated-skills | head  # only deletions, or empty after git rm

Done: 2026-10-20, uncommitted. `bootstrap --force` built all three: `ls build/` → aip-0.3a3
aip-0.6a1 dist; REFS.json holds aip-0.6a1 (aip 7d0655e, aip-spec 9edbf48, format 0.6a1),
aip-0.3a3 (aip 2c20a02, format 0.3a3), dist (distillation @ acb061d, clean); `aip-spec
--version` 0.6a1; wheels aip_spec-0.6a1 and aip-0.6a1; `build/aip-0.3a3/skill/aip/scripts/`
has validate.py and validate_schema.py; `build/dist/skill/skill-distillation/`. Gate smoke:
each variant's gate rejects the other variants' authoring skills with its own error kinds
(dist: no source/, unresolved paths; 0.3a3: missing_aip_spec; 0.6a1: missing_runtime_block).
647 tracked files under generated-skills/ removed from the index (`git rm -rf`). Files:
`_variants.py` (new), `_aip.py` (rewritten per variant), `cli.py` (bootstrap rewritten;
convert/eval pinned to aip-0.6a1 until S2/S3), `_authoring.py`, `run_matrix.py`,
`scripts/campaign.py` (import-level changes only).

## S2. Compile per variant: convert, batch-convert, prompts, instruction staging  [x]

Changes:

- `cli.py convert --task T --variant V [--force] [--author-model claude-opus-5-5]
  [--stage-data full]`. `--from` and `--single/--per-skill` go away: every compile is
  curated-side and single. Output `generated-skills/T/V/<skill-name>/`, record
  `_authoring/V/single/`. Default author model `claude-opus-5-5`.
- `_authoring.py`: `make_workspace(task, variant)` copies `build/V/skill/<name>` to
  `.claude/skills/<name>/`; `stage_curated` also copies the task's `instruction.md` to
  `inputs/instruction.md`; `meta.json` records `variant`, `stage_instruction: true`,
  `stage_data`, and the variant's REF block. The audit's allowed prefixes gain
  `build/<variant>/src/` (the author may read the tool's own source, as today).
- Prompts, one shared body plus a per-variant checklist note (`_prompts.py`, keyed by
  variant kind so a later aip release reuses the aip note). Two rules the body states
  for every variant, found while writing it: the author never spawns sub-agents or
  `claude -p` sessions, because a nested session's tool calls are outside the audited
  transcript (the 0.3a3 and distillation checklists both suggest fresh agents for the
  functional test; the 0.6a1 note already tested with `aip run`); and the staged inputs
  are described per `--stage-data`, fixing the old note that called full-data inputs
  truncated samples. The note:
  - Shared: compile the curated skills under `./inputs/skills/` into ONE skill at
    `./out/<skill-name>/`; `./inputs/instruction.md` is the task statement a downstream
    agent receives, use it to understand what the skill must achieve, and the pack must
    compute its answer from whatever files it is given, never hardcode one; copy the
    originals into `source/` with `source/README.md` (provenance, component choices,
    drop log); nobody is watching, never ask, write only under `./out/` and `./scratch/`.
  - `aip-0.6a1`: today's `_CHECKLIST_NOTE`, re-read against `build/aip-0.6a1/skill/aip/
    SKILL.md` (0.6a1: type agreement) and corrected where it still says 0.6a0.
  - `aip-0.3a3`: follow that skill's checklist; validate with
    `python ./.claude/skills/aip/scripts/validate.py ./out/<skill-name>`; whatever
    functional-test story the 0.3a3 skill describes, done inside `./scratch/`.
  - `dist`: follow the distillation skill's procedure, with these overrides: pick the
    skill name yourself (kebab-case, no questions), skip the install step and write
    straight to `./out/<skill-name>/`, do the functional test yourself inside
    `./scratch/` (no fresh agents, see above), and never pause for confirmation;
    `compatibility` names what the scripts need; scripts run in the task's container
    (see `./inputs/environment/Dockerfile`).
- `batch-convert --variant V` (repeatable) `--task T ...`, skips tasks whose pack exists
  and passes V's gate unless `--force`; `_already_done(task, variant)`.
- `scripts/compile-collection.sh N --variant V`; `scripts/campaign.py to-compile N
  --variant V` and `check N --variant V`; collection names gain `ablation`
  (`configs/campaign-ablation.yaml`, written in S3; for S2's proof use `--task`).

Proof (one task, three variants, about $6-12):

    for v in dist aip-0.3a3 aip-0.6a1; do
      uv run aip-skillbench convert --task exoplanet-detection-period --variant $v --force
    done
    ls -d generated-skills/exoplanet-detection-period/*/*/            # three packs
    for v in dist aip-0.3a3 aip-0.6a1; do
      python3 -c "import json;d=json.load(open('generated-skills/exoplanet-detection-period/_authoring/$v/single/meta.json'));print('$v',d['variant'],d['stage_instruction'],d['author_model'],d['claude_exit'])"
      python3 -c "import json;print('$v audit ok:',json.load(open('generated-skills/exoplanet-detection-period/_authoring/$v/single/audit.json'))['ok'])"
    done
    ls generated-skills/exoplanet-detection-period/_authoring/*/single/   # prompt.md transcript.jsonl audit.json meta.json
    grep -c "inputs/instruction.md" generated-skills/exoplanet-detection-period/_authoring/*/single/prompt.md
    # the dist pack is not an AIP pack:
    ! grep -q "AIP runtime" generated-skills/exoplanet-detection-period/dist/*/SKILL.md
    # the 0.3a3 pack is 0.3a3, the 0.6a1 pack is 0.6a1:
    grep -h "aip" generated-skills/exoplanet-detection-period/aip-0.3a3/*/SKILL.md | head -3
    grep -h "aip-version" generated-skills/exoplanet-detection-period/aip-0.6a1/*/SKILL.md

Done: 2026-10-20, uncommitted. `batch-convert --task exoplanet-detection-period --variant
dist --variant aip-0.3a3 --variant aip-0.6a1 --concurrency 3 --force --yes`: 3 succeeded in
38.8 min wall clock. Per variant (meta.json / audit.json): stage_instruction=True,
stage_data=full, author claude-opus-5-5, claude_exit=0, audit ok, 0 violations;
aip-0.6a1: 52 tool calls, $3.56, 29 min, pack transit-period-finder (5 scripts, 1 asset,
1 reference, source/ incl. the task instruction); aip-0.3a3: 42 calls, $2.87, 36 min,
transit-period-finder (1 script, source/procedure.schema.json bundled,
metadata.aip.spec/schemaId); dist: 44 calls, $2.90, 39 min, transit-period-search (1
script, Trigger When / Purpose / checklist body, `compatibility` names the packages, no
runtime block, no aip-version). Every prompt.md names ./inputs/instruction.md. `campaign.py
check 1 --variant V` → "1 ok, 0 failing" for all three. Total $9.33 for the three packs.
Files: `_prompts.py` (new), `_authoring.py`, `cli.py` (convert, batch-convert),
`scripts/campaign.py` (--variant), `scripts/compile-collection.sh` (--variant).

## S3. The `skill` mode, scenarios in run-matrix, campaign config and scripts  [x]

Changes:

- `cli.py eval --mode skill --variant V [--nudge/--no-nudge]` mounts
  `generated-skills/T/V/` as the skills dir after V's gate passes; `--nudge` (default off)
  writes the mounted-skill memory text (today's `aip-spec` text, renamed `skill` in
  `_benchflow_patch.NUDGE_MEMORY`). `--mode aip-runtime --variant V` (V must be an aip
  variant with wheels and a runtime skill; refused for `dist` and `aip-0.3a3`) does what
  it does today with V's wheels, runtime skill, and pack; `--aip-nudge` default on.
  `--decision-model` unchanged. `Mode` loses `aip_spec`, `aip_from_instruction`,
  `aip_from_curated`, `model_dist`; `--variant` is refused outside `skill` and
  `aip-runtime`.
- `run_matrix.py`: config `scenarios:` list of `{name, mode, variant, nudge}`; `modes:`
  still accepted as shorthand for scenarios without a variant. `Cell` gains `scenario`;
  keys and dir names use the scenario name; `summary.jsonl`/`csv` rows carry `scenario`,
  `mode`, `variant`; `campaign.json` records the scenarios and `refs` (the contents of
  `generated-skills/REFS.json`); `_validate_generated_skills` checks each (task, variant)
  with the variant's gate before any cell runs; the matrix view has one column per
  scenario; `--scenario NAME` repeatable on the CLI filters the config's list.
- `scripts/campaign.py`: collections gain `ablation`; `report` groups by scenario and
  prints the AIP signals for scenarios whose variant is an aip variant (json_steps and
  aip_mentions for `skill`, search/run/resume/done for `aip-runtime`) and `skill=` for
  every mounted-skill scenario, so a solver that ignored the pack is visible.
- `configs/campaign-ablation.yaml`: the 28 tasks after the four swaps
  (fix-build-agentops, software-dependency-audit, exam-block-sequencing, jpg-ocr-stat
  in; google-auto, suricata, civ6, enterprise-information-search out), `models:
  [claude-haiku-5-5]`, `agent_env: [MAX_THINKING_TOKENS=0]`, `trials: 5`,
  `concurrency: 10`, `decision_model: false`, and

      scenarios:
        - {name: human,    mode: human-curated}
        - {name: dist,     mode: skill,       variant: dist}
        - {name: aip-v03,  mode: skill,       variant: aip-0.3a3}
        - {name: aip-spec, mode: skill,       variant: aip-0.6a1}
        - {name: aip-rt,   mode: aip-runtime, variant: aip-0.6a1}

- `scripts/run-campaign.sh ablation` and `compile-collection.sh ablation --variant V`.
- Docs: `README.md` mode table, `skill-modes.md`, `docs/campaigns.md` updated to the new
  modes and the scenario config; `run-matrix.md` config example.

Proof (spends nothing):

    uv run aip-skillbench eval --help | grep -E "^\s+--(mode|variant|nudge)"
    uv run aip-skillbench eval --task x --model m --mode noskill --variant dist 2>&1 | tail -1   # refused
    uv run python scripts/campaign.py tasks ablation | wc -l                                      # 28
    uv run python scripts/campaign.py tasks ablation | grep -c -E "agentops|dependency-audit|exam-block|jpg-ocr"   # 4
    uv run python scripts/campaign.py check ablation --variant dist 2>&1 | tail -1                # 1 ok, 27 failing (only exoplanet compiled)
    # dry listing: 700 cells, five scenario columns, no spend (needs a --dry-run on run-matrix, add it)
    uv run aip-skillbench run-matrix --config configs/campaign-ablation.yaml --dry-run | tail -3

Done: 2026-10-20, uncommitted (done ahead of S2's proof, which waits on three Opus compiles).
`eval --help` lists `--mode [noskill|human-curated|selfgen-skill-creator|skill|aip-runtime]`,
`--variant`, `--nudge/--no-nudge`, `--aip-nudge/--no-aip-nudge`. Refusals: `--variant` with
noskill; `--mode skill` without a variant; `aip-runtime --variant dist` ("has no runtime");
`--nudge` with human-curated. `campaign.py tasks ablation` → 28, 4 replacements present;
`check ablation --variant dist` → "0 ok, 28 failing" (no packs yet). `run-matrix --config
configs/campaign-ablation.yaml --dry-run` → five scenarios (human/dist/aip-v03/aip-spec
with nudge=off, aip-rt with nudge=on), 700 cells, first command shown. `campaign.py
report` still reads the 2026-10-06 campaign dir (rows without a scenario fall back to
mode). Files: `run_matrix.py` (rewritten: Scenario, scenario-keyed cells, `--dry-run`,
refs in campaign.json), `cli.py` (Mode enum, eval, run-matrix), `_benchflow_patch.py`
(`NUDGE_MEMORY["skill"]`), `scripts/campaign.py` (report by scenario),
`configs/campaign-ablation.yaml`, `scripts/run-campaign.sh`, and the docs: README,
skill-modes.md, docs/campaigns.md, run-matrix.md.

## S4. Smoke test: one task through all five scenarios; the replacement images  [x]

Changes: none expected; this step finds what S1-S3 missed. Fixes land as part of S4.

Proof (about $1 and the four image builds):

    # exoplanet-detection-period has all three packs from S2
    OUT=runs/smoke-ablation-$(date +%F)
    uv run aip-skillbench run-matrix --config configs/campaign-ablation.yaml \
      --task exoplanet-detection-period --trials 1 --concurrency 5 --out "$OUT" --yes
    uv run python scripts/campaign.py report "$OUT"
    # expected: five rows, status pass or fail (no error); human: no skill from a pack, no aip;
    # dist / aip-v03 / aip-spec: skill=<pack name>, aip_mentions=0, and for aip-spec json_steps >= 1;
    # aip-rt: skill=aip-runtime, search>=1, run/resume>=1, done=yes; timing.json has only
    # memory_file among the extras for aip-rt and nothing extra for the mounted-skill rows.
    # the four replacements build, and the agentops image's Python decides the fallback:
    for t in fix-build-agentops software-dependency-audit exam-block-sequencing jpg-ocr-stat; do
      uv run aip-skillbench eval --task $t --model claude-haiku-5-5 --mode noskill \
        --agent-env MAX_THINKING_TOKENS=0 --jobs-dir jobs/smoke-$t
    done
    docker images | grep -E "agentops|dependency-audit|exam-block|jpg-ocr"
    docker run --rm <agentops image> python3 --version      # >= 3.10 keeps agentops; else gh-repo-analytics

Done: (partial, 2026-10-20) The four replacement images built and one noskill Haiku 5.5
trial each ran to a verdict with no errors: fix-build-agentops 0 (31 tools, 543 s, 254 s
of it the image build), software-dependency-audit 0 (6 tools, 85 s), exam-block-sequencing
1 (22 tools, 937 s), jpg-ocr-stat 0 (15 tools, 164 s). benchflow keeps no task image
after a trial on this version, so the Python check came from the agentops trajectory:
the container reports Python 3.10.12 and 3.11.9, so the aip client installs and
fix-build-agentops stays (no gh-repo-analytics fallback).

Smoke, 2026-10-20, `runs/smoke-ablation-2026-10-20` (`run-matrix --config
configs/campaign-ablation.yaml --task exoplanet-detection-period --trials 1 --concurrency 5`):
five cells, five passes, no errors, about 3 min each (dist 4 min).

| scenario | reward | tools | wall s | signals | timing extras |
|---|---|---|---|---|---|
| human | 1 | 10 | 164 | skill=- | none |
| dist | 1 | 4 | 255 | skill=transit-period-search | none |
| aip-v03 | 1 | 6 | 168 | skill=transit-period-finder, json_steps=0, aip_mentions=0 | none |
| aip-spec | 1 | 5 | 166 | skill=transit-period-finder, json_steps=3, aip_mentions=0 | none |
| aip-rt | 1 | 6 | 171 | search=1, run/resume=2, paused=1, done=yes (`aip run transit-period-finder@e6edf7c5…`) | aip_install 12.3, aip_server 1.2, aip_publish 0.7, memory_file 0.1 |

Two readings differ from the proof's expectation and are measurements, not harness
faults: `skill=-` for human and aip-rt means no Skill-tool launch was recorded; in
campaign 28 the same held for 5/5 aip-spec and 5/5 aip-runtime cells on this task and
133/140 human-curated cells, since the solver reads SKILL.md directly. The launch
signal only counts explicit Skill-tool calls. `campaign.json` records the five
scenarios and the three variants' REFS blocks; `summary.jsonl` rows carry scenario,
mode, variant.

Follow-up found here, not fixed: `--bake-agent` (default on) appends its install layer
to the task's Dockerfile and writes `environment/_deps/install-agent.sh` in place, and
benchflow's environment dir is the vendored task folder, so every first trial of a task
dirties `vendor/skillsbench` (the submodule the README calls read-only). Idempotent and
harmless for trials. Handling chosen 2026-10-20: `.gitmodules` sets `ignore = dirty` on
the submodule, so the parent repo stops reporting those edits (a changed submodule
commit is still reported). The edits themselves stay in the working tree; a bake that
stages a copy or reverts itself after the build is a later cleanup, not needed for S5/S6.

## After this plan

S5 compiles the cohort (`compile-collection.sh ablation --variant V` for each V, about
$170-340) and commits `generated-skills/`; S6 runs `run-campaign.sh ablation` (700 cells,
about $120, 10-12 h). Both are started by hand after this plan is done and reviewed.
