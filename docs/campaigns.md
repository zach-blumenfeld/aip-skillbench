# Campaigns: a task collection under a set of scenarios

A campaign runs every task in a collection under each of its scenarios (a solver mode
plus, for `skill` and `aip-runtime`, the compile variant whose pack the container gets
and whether the memory nudge is written; see [skill-modes.md](../skill-modes.md)), with
one solver model and N trials per (task, scenario). Packs are compiled once per task per
variant with Opus and committed under `generated-skills/<task>/<variant>/`; two
scenarios on the same variant use the same pack bytes.

| File | What it is |
|---|---|
| `configs/campaign-{1,5,10,27,ablation}.yaml` | the collection's tasks plus the campaign settings |
| `scripts/compile-collection.sh N --variant V` | compile (author) the V packs a collection still needs, then check them |
| `scripts/run-campaign.sh N` | run the campaign with `run-matrix` and print its summary |
| `scripts/campaign.py` | the helper both scripts call (task lists, gate sweep, report) |

The current campaign is `ablation` (`configs/campaign-ablation.yaml`): the five
scenarios of [aip-version-ablation-benchmark.md](aip-version-ablation-benchmark.md)
(`human`, `dist`, `aip-v03`, `aip-spec`, `aip-rt`) on 28 tasks, `claude-haiku-5-5` with
`agent_env: [MAX_THINKING_TOKENS=0]`, `trials: 5`, `concurrency: 10`, `decision_model:
false` (decision steps pause and the solver answers): 700 cells. The older collections
(1, 5, 10, 27) still list `modes: [human-curated, aip-spec, aip-runtime]` from the 0.5a1
campaigns; `aip-spec` is no longer a mode (it is `skill` on variant `aip-0.6a1`), so they
need their `modes:` rewritten as `scenarios:` before they run again.

## The collections

Collections nest: each one is the previous one plus the tasks listed. Difficulty is the
task's own `task.toml`; "skills" is the number of curated skills under
`environment/skills/` that the pack is compiled from. No task needs extra credentials.

**campaign-1** (1 task)

| task | difficulty | skills |
|---|---|---|
| exoplanet-detection-period | medium | 5 |

**campaign-5** (5 tasks): campaign-1 plus

| task | difficulty | skills |
|---|---|---|
| 3d-scan-calc | hard | 1 |
| earthquake-plate-calculation | medium | 1 |
| energy-market-pricing | hard | 4 |
| financial-modeling-qa | hard | 2 |

**campaign-10** (10 tasks): campaign-5 plus

| task | difficulty | skills |
|---|---|---|
| civ6-adjacency-optimizer | hard | 4 |
| court-form-filling | easy | 1 |
| crystallographic-wyckoff-position-analysis | medium | 2 |
| dialogue-parser | easy | 1 |
| powerlifting-coef-calc | easy | 3 |

**campaign-ablation** (28 tasks): campaign-27 with four swaps, each in its difficulty and
category (reasons in the spec): fix-build-agentops for fix-build-google-auto,
software-dependency-audit for suricata-custom-exfil, exam-block-sequencing for
civ6-adjacency-optimizer, jpg-ocr-stat for enterprise-information-search.

**campaign-27** (28 tasks; the name is historical: the list grew by one): campaign-10 plus

| task | difficulty | skills |
|---|---|---|
| adaptive-cruise-control | medium | 5 |
| bike-rebalance | medium | 4 |
| dapt-intrusion-detection | hard | 2 |
| data-to-d3 | medium | 1 |
| drone-planning-control | medium | 6 |
| energy-unit-commitment | hard | 3 |
| enterprise-information-search | hard | 1 |
| fix-build-google-auto | easy | 3 |
| grid-dispatch-operator | medium | 3 |
| jax-computing-basics | medium | 1 |
| mars-clouds-clustering | hard | 3 |
| offer-letter-generator | easy | 1 |
| parallel-tfidf-search | medium | 3 |
| protein-expression-analysis | medium | 1 |
| sec-financial-report | hard | 2 |
| spring-boot-jakarta-migration | hard | 5 |
| suricata-custom-exfil | medium | 3 |
| travel-planning | medium | 6 |

## Setting up a machine (fresh VM or an existing clone)

```sh
# existing clone: get onto the branch and the vendored tasks it expects
cd ~/aip-skillbench
git fetch origin && git checkout aip-0.4a0 && git pull
git submodule update --init                 # vendor/skillsbench at the pinned commit
git clean -fdn generated-skills             # dry run: stale dirs from an older checkout
git clean -fd generated-skills              # remove them (git keeps no empty dirs, so leftovers survive a checkout)

# toolchain
uv sync
export PATH="$HOME/.local/bin:$PATH"        # uv tool installs land here; add to ~/.bashrc
uv run aip-skillbench bootstrap --force     # clones aip + aip-spec over SSH (git@github.com),
                                            # installs the aip and aip-spec CLIs, builds the wheels
cp /path/to/.env .                          # ANTHROPIC_API_KEY (gitignored; copy it over)

# check
aip-spec --version                          # 0.5a1
ls build/aip                                # aip_spec-*.whl and aip-*.whl
python3 -c "import json;d=json.load(open('generated-skills/REFS.json'));print({k:v.get('format_version') for k,v in d.items()})"
ls -d generated-skills/*/{dist,aip-0.3a3,aip-0.6a1}/*/ | wc -l                 # 84 for the ablation cohort
for v in dist aip-0.3a3 aip-0.6a1; do uv run python scripts/campaign.py check ablation --variant $v | tail -1; done
docker info --format 'cpus={{.NCPU}} mem={{.MemTotal}}'
```

`bootstrap` clones over SSH; the machine needs a GitHub key (`ssh -T git@github.com`),
or switch the two `*_REMOTE` constants in `aip_skillbench/_aip.py` to `https://` URLs.
The `claude` CLI is only needed to compile packs, not to run campaigns. For a GCP VM,
`scripts/gcp-docker-setup.md` has the Docker daemon settings that matter at
concurrency 12 and up. Each task's first trial builds its image with the agent baked
in (about two minutes, once); a slow network makes that and the tasks' own verifier
downloads the bottleneck, so run campaigns where bandwidth is good.

### The ablation campaign on the 28 tasks

```sh
OUT=runs/campaign-ablation-$(date +%F)
caffeinate -dimsu uv run aip-skillbench run-matrix \
  --config configs/campaign-ablation.yaml --out "$OUT" --yes
# or a subset of its scenarios:
caffeinate -dimsu uv run aip-skillbench run-matrix \
  --config configs/campaign-ablation.yaml --scenario aip-spec --scenario aip-rt --out "$OUT" --yes
```

The config's `agent_env: [MAX_THINKING_TOKENS=0]` runs the solver with extended thinking
off; it is required for Claude 5 models until `claude-agent-acp` ships an SDK that speaks
their thinking parameter, and it is recorded in `campaign.json`. Drop `caffeinate` on
Linux. Re-running the same command resumes; cells that errored are treated as done, so
after a bad run use a new `--out` or delete the directory.

## Running a campaign

Prerequisites: `uv sync`, `.env` with `ANTHROPIC_API_KEY` (the solver, and `claude -p`
for compiling), Docker Desktop running, and the `claude` CLI on PATH for compiling.

1. **Bootstrap once** (and again only when a variant's pins change):

   ```bash
   uv run aip-skillbench bootstrap
   cat generated-skills/REFS.json        # per variant: refs, shas, format version
   ```

2. **Compile the collection, per variant.** Authors one pack with Opus for every task
   whose pack under that variant is missing or fails the variant's gate, then runs the
   gate sweep and the `_authoring` audit over the whole collection. Tasks with a valid
   pack are skipped, so this is a no-op when the packs are already committed.

   ```bash
   bash scripts/compile-collection.sh N --variant V --dry-run   # what it would compile and spend; spends nothing
   bash scripts/compile-collection.sh N --variant V             # prints the estimate, waits 5 s (--yes skips the wait)
   bash scripts/compile-collection.sh N --variant V --force     # recompile every task in the collection
   ```

   It must end with every task `ok` (the gate clean, `audit.json` `"ok": true`). Commit
   `generated-skills/` (packs, `_authoring/`, `REFS.json`) before the campaign so the run
   is tied to committed pack bytes.

3. **Optional plumbing trial** on one task (about $0.10 and 5 min per scenario):

   ```bash
   uv run aip-skillbench run-matrix --config configs/campaign-ablation.yaml \
     --task exoplanet-detection-period --trials 1 --out runs/plumb-$(date +%F) --yes
   ```

4. **Run the campaign:**

   ```bash
   bash scripts/run-campaign.sh N                   # extra run-matrix flags pass through, e.g. --shuffle
   ```

   This runs `run-matrix --config configs/campaign-N.yaml --out runs/campaign-N-<date>
   --yes` under `caffeinate -dimsu` (macOS; skipped where absent), then prints the
   per-mode summary and one line per AIP cell. It exits 1 if any cell errored.

5. **Read the results** in `runs/campaign-N-<date>/` (below). Re-print the report any
   time with `uv run python scripts/campaign.py report runs/campaign-N-<date>`.

### Resuming

Re-running the same command resumes: `run-matrix` skips every cell already recorded in
`summary.jsonl` (passes, fails, and errors alike). The output directory carries the
start date, so to resume on a later day name it explicitly:
`CAMPAIGN_OUT=runs/campaign-5-2026-10-07 bash scripts/run-campaign.sh 5`. To retry the
cells that errored, see `scripts/retry_errors.py`; `--force` re-runs every cell.

## Cost and wall clock

Compile (Opus 4.7 under the 0.5a1 checklist, measured 2026-10-06: $2–4 and 10–15 min per
task, concurrency 5):

| collection | compile cost | compile wall clock |
|---|---|---|
| 1 | ≈ $3 | ≈ 12 min |
| 5 | ≈ $15 | ≈ 15 min |
| 10 | ≈ $30 | ≈ 25 min |
| 27 | ≈ $60–100 | ≈ 60 min |

Campaign (3 modes × 5 trials on Haiku, concurrency 10):

| collection | cells | cost | wall clock |
|---|---|---|---|
| 1 | 15 | ≈ $3 | ≈ 15 min |
| 5 | 75 | ≈ $12 | ≈ 1 h |
| 10 | 150 | ≈ $25 | ≈ 2 h |
| 27 | 420 (28 tasks) | ≈ $70 | 6–8 h |

A `human-curated` cell can run to the 1800 s agent budget; that is a benchflow timeout,
not a harness bug.

## Watching a run

`run-matrix` draws its live matrix (one row per task, one glyph per trial, per-mode
aggregates) in the terminal it runs in. It needs a TTY: under `nohup`, in the
background, or through `tee` nothing is drawn. On a VM run it inside `tmux` so the view
survives an SSH drop (`tmux new -s bench`, later `tmux attach -t bench`).

The same view can be rebuilt from the run's files in any other terminal, during or
after the run:

```sh
uv run aip-skillbench matrix-view --watch        # newest campaign under runs/, refreshes every 10 s
uv run aip-skillbench matrix-view runs/<dir>     # one snapshot of a given run
```

A cell shows as running when its `cells/<cell>/` dir exists but no summary row does.

## Reading the results

`runs/campaign-N-<date>/` holds:

- `campaign.json`: the settings the run started with: tasks, models, scenarios (name,
  mode, variant, nudge), trials, concurrency, agent, sandbox, `decision_model`,
  `agent_env`, and `refs` (each used variant's block from `REFS.json`, with its commit
  shas). Rewritten on each resume with that resume's `already_done_at_start`/`to_run`.
- `summary.csv` / `summary.jsonl`: one row per finished cell: `task, model, scenario,
  mode, variant, trial, status` (`pass` = reward ≥ 1, `fail`, or `error` = no usable `result.json`), `reward`,
  `n_tool_calls`, `wall_clock` (seconds), `error`, `trial_dir` (the benchflow trial
  directory), timestamps, `subprocess_rc`. A resumed cell that was re-run appears twice;
  the last row wins.
- `status.json`: live counts. `logs/<cell>.log`: each `eval` call's output.
  `cells/<cell>/`: the benchflow jobs, with `result.json`, `timing.json`,
  `agent/acp_trajectory.jsonl`, and `verifier/reward.txt` in the trial directory.

The report's per-AIP-cell signals come from `agent/acp_trajectory.jsonl`. The trajectory
keeps each terminal call's description and output, not its command line, so `aip` calls
are recognised by what they print.

### Audit signals per scenario

| scenario | what should be true | where to look |
|---|---|---|
| `human` | the task's own skills only; no `aip` anywhere | report: `skill=<a curated skill>`; `timing.json` has no `aip_*` keys and no `memory_file` |
| `dist` | the dist pack is launched as a skill; no `aip` anywhere | report: `skill=<pack name>`; no extras in `timing.json` |
| `aip-v03` | the 0.3a3 pack is launched as a skill; no `aip` command | report: `skill=<pack name>`, `aip_mentions=0`; no extras in `timing.json` |
| `aip-spec` | the 0.6a1 pack is launched as a skill and its step scripts run with JSON state on stdin, each printing a JSON object; no `aip` command | report: `skill=<pack name>`, `json_steps` ≥ the graph's execution steps, `aip_mentions=0`; no extras in `timing.json` (no nudge) |
| `aip-rt` | only the generic `aip-runtime` skill is mounted; the solver runs `aip search` → `aip info` → `aip run <name>` (by name, not a folder) → `aip resume` per pause, reaching `"done": true` | report: `skill=aip-runtime`, `search` ≥ 1, `run/resume` ≥ 1, `done=yes`; `timing.json` has `aip_install`, `aip_server`, `aip_publish`, `memory_file` |

An `aip-runtime` cell with `done=NO` means the solver abandoned the protocol or the run
failed (`failed` counts `aip: <error>` outputs); that is a measurement, not a harness
failure. Likewise a pack that runs cleanly and computes a wrong answer is a benchmark
result: never edit, tune, or recompile a pack to make a trial pass.

Scripts run as the `agent` user in every scenario (the aip-rt server runs none; the
solver's client does); outputs land under `/root/`, which the verifier reads.

## Standing rules

- Never commit anything under `skill-analysis/` (untracked analysis files).
- `generated-skills/REFS.json` pins every variant's repos; commit it with the packs.
  Reproduce a variant exactly with
  `uv run aip-skillbench bootstrap --variant V --force --aip-sha <aip.sha from REFS.json>`.
- `build/` is disposable: `bootstrap` rebuilds every variant, and the authoring
  workspaces under `build/authoring/` are scratch.
- `runs/` and `jobs/` are not committed.
- Each variant's gate is its own validator; the `aip-0.6a1` gate rejects any pack with
  an outdated runtime block, so a campaign never mixes block versions within a variant.
