# Campaigns: the three AIP 0.5a1 modes at 1, 5, 10, or 27 tasks

A campaign runs every task in a collection under three modes (`human-curated`,
`aip-spec`, `aip-runtime`; see [skill-modes.md](../skill-modes.md)) with Haiku 4.5 as
the solver, 5 trials per (task, mode). The AIP packs are compiled once per task with Opus
and committed under `generated-skills/<task>/aip-from-curated/`; `aip-spec` and
`aip-runtime` use the same pack bytes.

| File | What it is |
|---|---|
| `configs/campaign-{1,5,10,27}.yaml` | the collection's tasks plus the campaign settings |
| `scripts/compile-collection.sh N` | compile (author) the packs a collection still needs, then check them |
| `scripts/run-campaign.sh N` | run the campaign with `run-matrix` and print its summary |
| `scripts/campaign.py` | the helper both scripts call (task lists, validation, report) |

Every config uses `models: [claude-haiku-4-5]`, `modes: [human-curated, aip-spec,
aip-runtime]`, `trials: 5`, `concurrency: 10`, `decision_model: false` (decision steps
pause and the solver answers), `aip_nudge: true` (the mode's memory file is written in
AIP cells), `agent: claude-agent-acp`, `sandbox: docker`.

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

## Running a campaign

Prerequisites: `uv sync`, `.env` with `ANTHROPIC_API_KEY` (the solver, and `claude -p`
for compiling), Docker Desktop running, and the `claude` CLI on PATH for compiling.

1. **Bootstrap once** (and again only when the AIP pins change):

   ```bash
   uv run aip-skillbench bootstrap
   cat generated-skills/AIP_REF.json     # aip sha, aip-spec ref, aip_version 0.5a1
   ```

2. **Compile the collection.** Authors a `--single` pack with Opus for every task whose
   pack is missing or fails validation, then runs the validation sweep and the
   `_authoring` audit over the whole collection. Tasks with a valid pack are skipped, so
   this is a no-op when the packs are already committed.

   ```bash
   bash scripts/compile-collection.sh N --dry-run   # what it would compile and spend; spends nothing
   bash scripts/compile-collection.sh N             # prints the estimate, waits 5 s (--yes skips the wait)
   bash scripts/compile-collection.sh N --force     # recompile every task in the collection
   ```

   It must end with every task `ok` (`aip-spec validate` clean, `audit.json` `"ok": true`).
   Commit `generated-skills/` (packs, `_authoring/`, `AIP_REF.json`) before the campaign
   so the run is tied to committed pack bytes.

3. **Optional plumbing trial** on one task (about $0.10 and 5 min per mode):

   ```bash
   uv run aip-skillbench eval --task exoplanet-detection-period --model claude-haiku-4-5 \
     --mode aip-runtime --jobs-dir jobs/plumb-aip-runtime
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

## Reading the results

`runs/campaign-N-<date>/` holds:

- `campaign.json`: the settings the run started with: tasks, models, modes, trials,
  concurrency, agent, sandbox, `decision_model`, `aip_nudge`, `aip_version` (must be
  `0.5a1`), and `aip_ref` (the full contents of `AIP_REF.json`, including both commit
  shas). Rewritten on each resume with that resume's `already_done_at_start`/`to_run`.
- `summary.csv` / `summary.jsonl`: one row per finished cell: `task, model, mode, trial,
  status` (`pass` = reward ≥ 1, `fail`, or `error` = no usable `result.json`), `reward`,
  `n_tool_calls`, `wall_clock` (seconds), `error`, `trial_dir` (the benchflow trial
  directory), timestamps, `subprocess_rc`. A resumed cell that was re-run appears twice;
  the last row wins.
- `status.json`: live counts. `logs/<cell>.log`: each `eval` call's output.
  `cells/<cell>/`: the benchflow jobs, with `result.json`, `timing.json`,
  `agent/acp_trajectory.jsonl`, and `verifier/reward.txt` in the trial directory.

The report's per-AIP-cell signals come from `agent/acp_trajectory.jsonl`. The trajectory
keeps each terminal call's description and output, not its command line, so `aip` calls
are recognised by what they print.

### Audit signals per mode

| mode | what should be true | where to look |
|---|---|---|
| `human-curated` | the task's own skills only; no `aip` anywhere | trajectory; `timing.json` has no `aip_*` keys and no `memory_file` |
| `aip-spec` | the pack is launched as a skill and its step scripts run with JSON state on stdin, each printing a JSON object; no `aip` command | report: `skill=<pack name>`, `json_steps` ≥ the graph's execution steps, `aip_mentions=0`; `timing.json` has only `memory_file` among the extras |
| `aip-runtime` | only the generic `aip-runtime` skill is mounted; the solver runs `aip search` → `aip info` → `aip run <name>` (by name, not a folder) → `aip resume` per pause, reaching `"done": true` | report: `skill=aip-runtime`, `search` ≥ 1, `run/resume` ≥ 1, `done=yes`; `timing.json` has `aip_install`, `aip_server`, `aip_publish`, `memory_file` |

An `aip-runtime` cell with `done=NO` means the solver abandoned the protocol or the run
failed (`failed` counts `aip: <error>` outputs); that is a measurement, not a harness
failure. Likewise a pack that runs cleanly and computes a wrong answer is a benchmark
result: never edit, tune, or recompile a pack to make a trial pass.

Scripts run as root in `aip-runtime` (the in-container server runs them) and as the
`agent` user in `aip-spec`; outputs land under `/root/`, which the verifier reads.

## Standing rules

- Never commit anything under `skill-analysis/` (untracked analysis files).
- `generated-skills/AIP_REF.json` pins both AIP repos; commit it with the packs.
  `aip-0.5a0` is a branch, so reproduce a cohort with
  `uv run aip-skillbench bootstrap --force --aip-sha <aip.sha from AIP_REF.json>`.
- `build/` is disposable: `bootstrap` rebuilds the wheels and skills, and the authoring
  workspaces under `build/authoring/` are scratch.
- `runs/` and `jobs/` are not committed.
- The packs are format 0.5a1; the validation gate rejects any pack with an outdated
  runtime block, so a campaign never mixes block versions.
