# Prompt: first eval campaign — Haiku 4.5, 6 tasks, 5 trials

Hand the block below to a fresh Claude Code session in this repo. It will run
the first full `run-matrix` campaign end-to-end, monitor progress, and report
results.

---

You are running the first full eval campaign for aip-skillbench. Background:
this repo evaluates AIP-formatted skills against SkillsBench tasks across 5
"skill modes" (noskill, human-curated, selfgen-skill-creator, aip-from-
instruction, aip-from-curated). The `aip-skillbench run-matrix` command runs
a (task × model × mode × trial) sweep concurrently. See run-matrix.md and
skill-modes.md for tool docs.

Repo: /Users/zach/dev/aip-skillbench

What to run:
  - Tasks: all 6 with AIP packs converted —
    3d-scan-calc, debug-trl-grpo, earthquake-phase-association,
    fix-druid-loophole-cve, taxonomy-tree-merge, video-silence-remover
  - Model: claude-haiku-4-5-20251001
  - Modes: all 5 (the default)
  - Trials: 5 per (task, mode)
  - Total: 6 × 5 × 5 = 150 cells
  - Concurrency: 4
  - Expected wall clock: ~60–90 min
  - Expected cost: ~$10–15 in Anthropic tokens

Step 1 — pre-flight checks. Confirm Docker is running and has enough
headroom; abort if not.

  docker info | grep -E "Memory|CPUs"
  docker system df

Memory should be ≥ 12 GB. If `docker info` errors, tell the user to start
Docker Desktop and stop.

Step 2 — confirm AIP packs exist for all 6 tasks. The run-matrix pre-flight
will catch this, but it's nicer to verify upfront:

  for t in 3d-scan-calc debug-trl-grpo earthquake-phase-association \
           fix-druid-loophole-cve taxonomy-tree-merge video-silence-remover; do
    for sub in aip-from-instruction aip-from-curated; do
      found=$(find generated-skills/$t/$sub -name SKILL.md 2>/dev/null | head -1)
      [ -z "$found" ] && echo "MISSING: $t / $sub"
    done
  done

If anything prints "MISSING", stop and tell the user to run
`aip-skillbench convert` for those before proceeding.

Step 3 — write the config to configs/eval-1-haiku.yaml:

  tasks:
    - 3d-scan-calc
    - debug-trl-grpo
    - earthquake-phase-association
    - fix-druid-loophole-cve
    - taxonomy-tree-merge
    - video-silence-remover
  models:
    - claude-haiku-4-5-20251001
  trials: 5
  concurrency: 4
  agent: claude-agent-acp
  sandbox: docker

Step 4 — launch. Use caffeinate so the Mac doesn't sleep mid-run (this is a
long campaign). Run in the background so you can monitor:

  caffeinate -dimsu uv run aip-skillbench run-matrix \
    --config configs/eval-1-haiku.yaml \
    --out runs/eval-1-haiku \
    --yes

Step 5 — monitor. Check progress every ~10 min by reading status.json and
tailing summary.jsonl. Watch for:
  - Cells with status "error" — surface the `error` field; common causes
    are Docker compose build failures (OOM, network) and Anthropic 429s.
  - Long-running cells (>5 min) — could be a hung container.
  - Per-mode pass-rate divergence — modes 4 & 5 are experimental, expect
    some variance vs noskill/human-curated baselines.

  cat runs/eval-1-haiku/status.json
  tail -20 runs/eval-1-haiku/summary.jsonl | python3 -c "
  import sys, json
  for line in sys.stdin:
      r = json.loads(line)
      icon = {'pass':'✓','fail':'✗','error':'·'}.get(r['status'],'?')
      print(f\"{icon} {r['task']:30s} {r['mode']:25s} t{r['trial']}  r={r['reward']}  wall={r['wall_clock']}s\")"

Step 6 — when complete, report:
  - Total wall clock (from elapsed_sec in status.json or campaign start time)
  - Per-mode pass rate, mean reward, mean tool calls, mean wall clock
    (run-matrix prints this automatically; you can also recompute from
    summary.jsonl)
  - List of any cells with status "error" and their `error` field
  - Path to runs/eval-1-haiku/summary.jsonl and summary.csv

Quick analysis snippet for the final report:

  python3 - <<'PY'
  import json, collections
  from pathlib import Path
  rows = [json.loads(l) for l in
          Path("runs/eval-1-haiku/summary.jsonl").read_text().splitlines()
          if l.strip()]
  by_mode = collections.defaultdict(list)
  for r in rows:
      by_mode[r["mode"]].append(r)
  print(f"{'mode':25s}  n  pass  pass%   mean-r   mean-tools  mean-wall")
  for m, rs in by_mode.items():
      n = len(rs)
      p = sum(1 for r in rs if r["status"] == "pass")
      rewards = [r["reward"] for r in rs if r["reward"] is not None]
      tools   = [r["n_tool_calls"] for r in rs if r["n_tool_calls"] is not None]
      walls   = [r["wall_clock"] for r in rs if r["wall_clock"] is not None]
      print(f"{m:25s}  {n:>2}  {p:>4}  {p/n*100:>5.1f}%  "
            f"{sum(rewards)/len(rewards):>6.2f}   {sum(tools)/len(tools):>8.1f}  "
            f"{sum(walls)/len(walls):>8.1f}")
  errs = [r for r in rows if r["status"] == "error"]
  print(f"\nErrors: {len(errs)}")
  for r in errs[:10]:
      print(f"  {r['task']}/{r['mode']}/t{r['trial']}: {r['error'][:200]}")
  PY

If the user interrupts before completion, the campaign is fully resumable —
re-running the same `aip-skillbench run-matrix --config ... --out ... --yes`
command skips cells already in summary.jsonl.
