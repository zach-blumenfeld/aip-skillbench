# run-matrix

Run a `(task × model × mode × trial)` evaluation matrix concurrently with live progress. One `aip-skillbench eval` subprocess per cell, fanned out through a thread pool, results streamed to disk as each cell finishes.

For what each mode is, see [skill-modes.md](skill-modes.md). This doc is the runbook for batch execution.

## Quickstart

```bash
uv run aip-skillbench run-matrix \
  --task 3d-scan-calc \
  --task earthquake-phase-association \
  --model claude-haiku-4-5 \
  --trials 3 \
  --yes
```

Defaults: all 5 modes, concurrency 4, agent `claude-agent-acp`, sandbox `docker`. With the above: 2 tasks × 1 model × 5 modes × 3 trials = **30 cells**.

The campaign writes to `runs/<YYYY-MM-DD__HH-MM-SS>/`. Override with `--out`.

## Docker prerequisites

Every cell runs in its own Docker container, so Docker Desktop's resource limits are the floor on what your matrix can do. Defaults (~7.7 GB RAM, 64 GB disk) are tight for `-j 4` and break on heavier tasks.

**Recommended Docker Desktop settings** (Settings → Resources):

| Setting | Default | Recommended | Why |
|---|---|---|---|
| Memory | ~7.7 GB | **12–16 GB** | ~2 GB per concurrent cell. OOM during `pip install` shows up as opaque `compose build` failures. |
| Swap | 1 GB | 2–4 GB | Cheap insurance for build spikes. |
| Disk image size | 64 GB | **≥ 128 GB** | bench builds a fresh project per trial; image cache + dangling layers accumulate fast across 95 tasks × 5 modes × N trials. |
| CPUs | (system) | leave as-is | Rarely the bottleneck. |
| File sharing | VirtioFS | **VirtioFS** (verify in Settings → General) | osxfs makes host↔container IO during build painfully slow. |

The corpus is mostly lightweight (56/95 tasks use `ubuntu:24.04`, 24/95 use `python:3.12-slim`), but a few outliers (e.g. `debug-trl-grpo`, the suricata-based intrusion-detection task) need real headroom. No GPU is required — the solver model runs in Anthropic's cloud, the sandbox is CPU-only.

**Concurrency sizing rule of thumb**: ~2 GB RAM per slot. With 16 GB Docker memory, `-j 6` is comfortable. Above `-j 8` you'll start racing the Anthropic per-org rate limit for `claude-haiku-4-5`; the runner surfaces 429s as cell errors (`·` in the live table) without aborting.

**Pre-run sanity check**:

```bash
docker info | grep -E "Memory|CPUs"            # confirm new limits applied
docker system prune -af                         # clean slate before a big run
docker system df                                # confirm headroom
```

**Mid-run housekeeping** (separate shell, won't kill active containers):

```bash
docker system df                                # watch growth
docker system prune -f --filter "until=2h"      # prune stuff older than 2h
```

## Long / overnight runs (macOS)

A full 150-cell campaign runs 3–5 hours; the laptop must stay awake the whole time or Docker's VM pauses and the run stalls silently. Three things together keep it alive:

**1. `caffeinate` — block macOS sleep.**

```bash
caffeinate -dimsu uv run aip-skillbench run-matrix \
  --config configs/eval-1-haiku.yaml --out runs/eval-1-haiku --yes
```

Flags: `-d` display, `-i` idle, `-m` disk, `-s` system, `-u` declare user active. **`-s` only works on AC power** — if you're on battery and the threshold trips, the system will sleep regardless.

**2. Lid open, AC plugged in.** Closing the lid forces clamshell sleep even with `caffeinate` running, unless you have an external display + keyboard + mouse connected. The Docker Desktop VM pauses when the system sleeps, containers stall, wall clock burns for nothing.

**3. Terminal window must stay open.** When you close a terminal window, macOS sends `SIGHUP` to its child processes and kills the run. For overnight durability use `tmux` so you can detach and safely close the window:

```bash
tmux new -s eval-haiku
# inside tmux:
caffeinate -dimsu uv run aip-skillbench run-matrix \
  --config configs/eval-1-haiku.yaml --out runs/eval-1-haiku --yes
# Ctrl-b then d to detach. Close terminal. Lid open. Plug in. Sleep.
# Tomorrow:
tmux attach -t eval-haiku
```

**Nested tmux gotcha**: if you start `tmux new` from inside an already-active tmux session, the inner session's prefix is shadowed by the outer one — `Ctrl-b d` won't detach. Check with `echo $TMUX` *before* starting tmux. If nested, press the prefix twice: `Ctrl-b Ctrl-b d`.

**Monitoring from another shell** (won't disturb the run):

```bash
tail -f runs/eval-1-haiku/summary.jsonl     # stream completed cells
cat   runs/eval-1-haiku/status.json         # latest totals snapshot
```

**Safety net**: if anything kills the run (terminal closed, Docker crash, OS update, the cat sat on the keyboard), the same command in the morning resumes from `summary.jsonl` — no work lost.

## Flags

| Flag | Repeatable | Default | Notes |
|---|---|---|---|
| `--task` | yes | — | Task name under `vendor/skillsbench/tasks/`. |
| `--model` | yes | — | Agent-specific model string (e.g. `claude-haiku-4-5`, `gpt-5.2-codex`). |
| `--mode` | yes | all 5 | `noskill`, `human-curated`, `selfgen-skill-creator`, `aip-from-instruction`, `aip-from-curated`. |
| `--trials` | no | 1 | Repeats per `(task, model, mode)` cell. |
| `--concurrency` / `-j` | no | 4 | Max concurrent cells. Real limits are Docker daemon + Anthropic rate limit. |
| `--config` | no | — | YAML config (CLI flags override matching keys). |
| `--out` | no | `runs/<timestamp>` | Campaign output directory. |
| `--agent` | no | `claude-agent-acp` | Solver agent. |
| `--sandbox` | no | `docker` | `docker`, `daytona`, or `modal`. |
| `--yes` / `-y` | no | off | Skip the 5s confirm pause. |
| `--force` | no | off | Re-run cells already in `summary.jsonl`. |
| `--shuffle` | no | off | Randomize cell execution order. |

## YAML config (recommended for large runs)

When the task list outgrows the CLI, drop it into a config file:

```yaml
# configs/full-haiku.yaml
tasks:
  - 3d-scan-calc
  - earthquake-phase-association
  - bike-rebalance
  - debug-trl-grpo
models:
  - claude-haiku-4-5
modes:                       # optional — defaults to all 5
  - noskill
  - human-curated
  - selfgen-skill-creator
  - aip-from-instruction
  - aip-from-curated
trials: 5
concurrency: 4
agent: claude-agent-acp
sandbox: docker
```

```bash
uv run aip-skillbench run-matrix --config configs/full-haiku.yaml --yes
```

Any flag passed on the CLI overrides the matching key in the YAML.

## Pre-flight (fails fast, runs nothing)

Before any cell starts, the runner checks:

1. **Tasks exist** — every `--task` resolves under `vendor/skillsbench/tasks/`.
2. **AIP packs exist** — if `aip-from-instruction` or `aip-from-curated` is in the mode list, each task has at least one `generated-skills/<task>/aip-from-{instruction,curated}/<skill>/SKILL.md`. All missing packs are listed at once; nothing runs. **Run `aip-skillbench convert` or `aip-skillbench batch-convert` first.**
3. **API key present** — the env var for `--agent` (`ANTHROPIC_API_KEY` for `claude-agent-acp`, `OPENAI_API_KEY` for `codex-acp`, `GEMINI_API_KEY` for `gemini`) is set in the environment or `.env`.

Failure on any of these exits before launching subprocesses.

## Live progress

While running:

- **Header**: cells done/total, currently running, pass count, pass rate, elapsed.
- **Matrix table**: one row per `(task, model)`, one column per mode; each cell shows a glyph per trial — `▢` pending, `⟳` running, `✓` pass, `✗` fail, `·` error.
- **Per-mode aggregates**: rolling `n`, pass count + %, mean reward, mean tool calls, mean wall clock.

For headless monitoring from another shell:

```bash
tail -f runs/<campaign>/summary.jsonl       # one line per completed cell
cat   runs/<campaign>/status.json           # latest snapshot, rewritten each completion
```

## Output layout

```
runs/<campaign>/
├── campaign.json              # frozen plan + start time
├── summary.jsonl              # one line per completed cell (source of truth)
├── summary.csv                # mirror of summary.jsonl, easier for pandas
├── status.json                # live snapshot (totals only)
├── logs/
│   └── <task>__<model>__<mode>__t<N>.log    # subprocess stdout/stderr per cell
└── cells/
    └── <task>__<model>__<mode>__t<N>/        # benchflow's --jobs-dir per cell
        └── <bench-timestamp>/
            └── <rollout-name>/
                ├── result.json
                ├── verifier/reward.txt
                ├── agent/acp_trajectory.jsonl
                └── …
```

Each `summary.jsonl` line includes: `task`, `model`, `mode`, `trial`, `status` (`pass`/`fail`/`error`), `reward`, `n_tool_calls`, `wall_clock`, `error`, `jobs_dir`, `trial_dir`, `started_at`, `finished_at`, `subprocess_rc`.

## Resume

Re-running with the same `--out` skips cells already in `summary.jsonl`:

```bash
# First run dies halfway through
uv run aip-skillbench run-matrix --config configs/full-haiku.yaml --yes
# Pick up where it left off
uv run aip-skillbench run-matrix --config configs/full-haiku.yaml --yes
# → "already done: 47   to run: 13"
```

`--force` ignores the existing summary and re-runs everything; old entries remain in `summary.jsonl` (downstream analysis should dedupe on the latest `started_at` per `(task, model, mode, trial)`).

## Concurrency notes

- The outer pool runs `--concurrency` cells in parallel. Each cell shells out to `aip-skillbench eval --concurrency 1`, so each subprocess is exactly one trial in one Docker container.
- Mode-3 (`selfgen-skill-creator`) trials run a creator scene + solver scene inside one sandbox — ~2× the wall clock and tool-call cost of other modes, but they take the same one slot in the pool.
- Failures don't abort the campaign. A cell's `result.json::error` (or worker exception) is recorded and the live table shows `·`. Final exit code is `1` if any cell errored, `0` otherwise.

## Quick analysis

```bash
# Pass rate by mode for a campaign
python3 - <<'PY'
import json, collections
from pathlib import Path
rows = [json.loads(l) for l in Path("runs/<campaign>/summary.jsonl").read_text().splitlines() if l.strip()]
by_mode = collections.defaultdict(list)
for r in rows:
    by_mode[r["mode"]].append(r["reward"] or 0)
for m, rs in by_mode.items():
    print(f"{m:25s}  n={len(rs):3d}  pass-rate={sum(1 for r in rs if r >= 1.0) / len(rs):.2%}  mean-reward={sum(rs)/len(rs):.2f}")
PY
```

Or load `summary.csv` directly into pandas / DuckDB / a notebook.
