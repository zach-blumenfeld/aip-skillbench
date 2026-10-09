# Weak-solver plan: Qwen3.5-9B through the Claude Code harness

A fresh agent executes this plan one step at a time:

    /clear
    Implement the next unchecked step in @docs/weak-solver-plan.md. Verify it as the step says, tick it off, commit.

Each step is self-contained. Read "Context" and "Rules" first, then only the step you are on.

## Context

**Question.** Campaign 28 (`runs/campaign-28-aip-h55-nothink-2026-10-08/`, 28 tasks x 3 modes x
5 trials, solver `claude-haiku-5-5` with thinking off) showed the compiled AIP procedure carries
the lift (human 45%, aip-spec 74%, aip-runtime 66%), but server-side execution (aip-runtime) added
no reward over the solver executing the graph itself (aip-spec). On tasks where both work, spec
was already at ceiling: Haiku follows a correct graph fine. The runtime can only show lift against
a solver that *drifts* when executing the graph by hand. This plan tests that with a deliberately
weaker, cheaper, open-weight solver, which is also the audience the runtime is for: teams that run
cheaper models, possibly self-hosted for data sovereignty.

**Solver chosen: `Qwen/Qwen3.5-9B`** (Alibaba, Apache 2.0, 9B dense, 262k context, native tool
calling). On Artificial Analysis Intelligence Index v4.3.2 it scores 11 against roughly 20 to 29
for Haiku 5.5 with thinking off: two notches down. Hosted through Hugging Face Inference Providers
pinned to Together (US). Live providers for this model as of 2026-10-09: together, deepinfra,
featherless-ai (US) and ovhcloud (France). Never let the route fall to an unpinned default.
Fallbacks if the smoke test shows the model cannot drive the tool loop at all: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
(index 10, agent-trained MoE) then `google/gemma-4-31b` (index 15).

**How the harness reaches a non-Claude model.** The solver agent is `claude-agent-acp` (Claude
Code's SDK inside the task container). Claude Code honours `ANTHROPIC_BASE_URL`; Hugging Face's
router serves the Anthropic Messages protocol at `https://router.huggingface.co` (Claude Code
appends `/v1/messages` itself). Benchflow (`vendor` dependency, see
`.venv/lib/python3.12/site-packages/benchflow/agents/env.py` and `registry.py`) already maps
`BENCHFLOW_PROVIDER_BASE_URL -> ANTHROPIC_BASE_URL`, `BENCHFLOW_PROVIDER_API_KEY -> ANTHROPIC_AUTH_TOKEN`,
`BENCHFLOW_PROVIDER_MODEL -> ANTHROPIC_MODEL` for this agent, and explicit `agent_env` keys take
priority over anything it inherits from `.env`. Hugging Face's own Claude Code docs additionally set
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`
and `CLAUDE_CODE_SUBAGENT_MODEL` to the open model so Claude Code's side calls do not request
Claude tier names. The provider is pinned by suffix on the model id: `Qwen/Qwen3.5-9B:together`.

**Secrets.** Benchflow filters any env key containing KEY/TOKEN/SECRET out of each trial's
`config.json`. Our own `run-matrix` writes `agent_env` verbatim into `campaign.json`; step S1
fixes that. Tokens come from `.env` (`HF_TOKEN`), never from a CLI flag.

**Machine.** The GCP VM `zach-aip-skillbench` (n2-standard-16, us-central1-a) runs the campaigns.
Setup is in `docs/campaigns.md` ("Setting up a machine"). The campaign-28 results are on the VM
under `runs/`, so comparisons in S3 can read them directly.

**Haiku baseline on the 5 pilot tasks (campaign 28, passes out of 5):**

| task | human | aip-spec | aip-runtime |
|---|---|---|---|
| exoplanet-detection-period | 3 | 5 | 5 |
| 3d-scan-calc | 5 | 5 | 5 |
| earthquake-plate-calculation | 0 | 5 | 5 |
| energy-market-pricing | 3 | 5 | 5 |
| financial-modeling-qa | 0 | 5 | 5 |

None of these five tasks touches the known defects from the campaign-28 report (decision-resume
state gap, root-owned server outputs, Python 3.9 images), so a weak-solver result on them is clean
before Track B lands.

## Rules

- Work on branch `aip-0.4a0` in this repo. Commit each step; push only when the step says.
- Never write under `vendor/`, `.claude/`, or `generated-skills/` in this plan.
- Never put a token in a command line, a config file, a commit, or a run directory. `.env` only.
- Run every command in the foreground; do not background long runs. Use `tmux` for campaigns so
  an SSH drop does not kill them (`tmux new -s bench`, later `tmux attach -t bench`).
- Nobody is watching. Do not ask questions; if blocked, write `BLOCKED: <why>` under the step and stop.
- Keep `--agent-env MAX_THINKING_TOKENS=0` on every run: the bundled SDK's thinking parameter is
  what broke Haiku 5.5 through this harness, and the open model should not get a different setting.

## Steps

### S0. Machine ready and the Hugging Face route proven  [x]

1. On the VM: `export PATH="$HOME/.local/bin:$PATH"`, `git pull`, `uv sync`, then verify per
   `docs/campaigns.md`: `aip-spec --version` prints 0.5a1 and all 28 packs validate.
2. `.env` must contain `ANTHROPIC_API_KEY` (benchflow still requires it for this agent) and
   `HF_TOKEN` (a Hugging Face token with the "Make calls to Inference Providers" permission; the
   user adds it). Verify presence only: `grep -c '^HF_TOKEN=' .env` prints 1.
3. Prove the route from the VM with a direct request, reading the token from `.env`:

   ```sh
   set -a; . ./.env; set +a
   curl -s https://router.huggingface.co/v1/messages \
     -H "Authorization: Bearer $HF_TOKEN" -H "content-type: application/json" \
     -d '{"model":"Qwen/Qwen3.5-9B:together","max_tokens":40,"messages":[{"role":"user","content":"Reply with the single word ready."}]}'
   ```
   Expect a JSON response whose `content[0].text` contains "ready" and whose `model` names
   Qwen. If the router rejects the Bearer header, try `-H "x-api-key: $HF_TOKEN"` and record
   which one worked in this step's notes. If both fail, `BLOCKED`.
4. Confirm the provider pin is live: `curl -s "https://huggingface.co/api/models/Qwen/Qwen3.5-9B?expand[]=inferenceProviderMapping"`
   lists `together` with `"status": "live"`.

Verify: the four checks above pass. Record the working auth header in a note under this step.

Notes (2026-10-09, on `zach-aip-skillbench`):
- Check 1 passes: up to date with `aip-0.4a0`, `uv sync` clean, `aip-spec --version` is 0.5a1,
  28 of 28 packs validate.
- Check 2 passes: `.env` has exactly one `HF_TOKEN=` line and an `ANTHROPIC_API_KEY=` line.
- Check 3 passes once credits are on the account (the first attempt failed with "no remaining
  credits"). It returns HTTP 200 with `"model":"Qwen/Qwen3.5-9B"` and the final text block
  `ready`, in about 1 to 3 s; the first request after the top-up hung past 90 s and later ones
  were fast.
  - **Auth header: `Authorization: Bearer`**, which matches what Claude Code sends from
    `ANTHROPIC_AUTH_TOKEN`. `x-api-key` gets an HTML 401.
  - **The model always thinks.** Responses open with a `thinking` block whose signature is
    `"unsigned"`, and `"thinking":{"type":"disabled"}` is ignored. With `max_tokens` 40 the
    whole budget goes to thinking and no text comes back, so allow a large `max_tokens`.
    `MAX_THINKING_TOKENS=0` therefore does not stop Qwen's reasoning. Keep it anyway for parity,
    but in S1 and S2 watch for errors when Claude Code sends the unsigned thinking blocks back.
  - **Usage is wrong.** `usage.output_tokens` comes back as 1 however much the model wrote, so
    do not rely on the trajectories' token or cost figures for this solver.
- Check 4 passes: `together`, `deepinfra`, `featherless-ai` and `ovhcloud` all show `"status": "live"`.

### S1. Harness: `--provider hf` for eval and run-matrix  [x]

Add a `--provider` option (values: `anthropic` default, `hf`) to `eval` and `run-matrix` in
`aip_skillbench/cli.py`, config key `provider`, threaded through `run_matrix.py` into each cell's
`eval` call. When `hf`:

- Read `HF_TOKEN` from `.env` (reuse `_read_dotenv`); error clearly if missing.
- Add to the solver's agent env (via the same path `--agent-env` uses):
  `BENCHFLOW_PROVIDER_BASE_URL=https://router.huggingface.co`,
  `BENCHFLOW_PROVIDER_API_KEY=<token>`, `ANTHROPIC_AUTH_TOKEN=<token>`,
  `ANTHROPIC_API_KEY=<token>` (explicit override so the real Anthropic key is never sent to the
  router), and `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`,
  `ANTHROPIC_DEFAULT_OPUS_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL` all set to the `--model` string.
- The model string carries the provider pin (`Qwen/Qwen3.5-9B:together`). It contains `/` and
  `:`; make sure `Cell.safe_name` in `run_matrix.py` and any path built from the model in
  `cli.py` sanitise both characters (replace with `_`), and that `summary.csv` still records the
  full string.
- `campaign.json`: redact the value of any `agent_env` entry whose key contains KEY, TOKEN,
  SECRET or PASSWORD (write `<redacted>`), mirroring benchflow's `config.json` filter. Apply the
  same redaction to the `$ ...` command line echoed at the top of each `logs/<cell>.log`.
- `_validate_api_key` in `run_matrix.py` currently requires the Anthropic key for this agent;
  keep that (benchflow needs it) but, with `--provider hf`, also require `HF_TOKEN`.
- Document the option in `docs/campaigns.md` (a short "Running an open-weight solver" subsection:
  what it sets, where the token lives, the provider-pin syntax, the fallback models).

Verify:
1. `uv run aip-skillbench eval --task exoplanet-detection-period --mode human-curated --model Qwen/Qwen3.5-9B:deepinfra --provider hf --agent-env MAX_THINKING_TOKENS=0 --jobs-dir jobs/s1-check` runs one trial to completion (pass or fail is irrelevant here).
2. In that trial's `config.json`, `agent_env` shows `ANTHROPIC_BASE_URL=https://router.huggingface.co`, `ANTHROPIC_MODEL=Qwen/Qwen3.5-9B:together`, the four tier-model variables, and no key or token values.
3. `grep -rIl "$(grep '^HF_TOKEN=' .env | cut -d= -f2-)" jobs/s1-check runs 2>/dev/null` prints nothing (the token appears in no output file).
4. The trial's `agent/acp_trajectory.jsonl` contains at least one completed tool call and no 401/403/404 or "model not found" text. If the model's responses show thinking-parameter or tier-name errors, fix the env (not the model) and rerun.
5. `uv run pytest -q` (or the repo's existing test command) still passes.

Commit, then push (`git push origin aip-0.4a0`) so the VM and the laptop share it.

Notes (2026-10-09, on `zach-aip-skillbench`):
- Implemented in `aip_skillbench/_provider.py` (env, redaction, path sanitising), `cli.py`
  (`--provider` on `eval` and `run-matrix`, config key `provider`), `run_matrix.py` and
  `_benchflow_patch.py`. The secret entries (`BENCHFLOW_PROVIDER_API_KEY`,
  `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`) never go on a command line: `eval` passes
  them to the `bench` subprocess as JSON in `AIP_SKILLBENCH_SECRET_AGENT_ENV`, and a patch
  on `rollout.resolve_agent_env` merges them in as explicit keys. Redaction exempts
  `*_TOKENS` keys so `MAX_THINKING_TOKENS=0` stays visible in `campaign.json` and the
  cell logs (benchflow's own `config.json` filter still drops it).
- **Provider pin changed from `:together` to `:deepinfra`** (same model, still US). The
  first check run on `:together` ended after 1 tool call: the model wrote its next call as
  `<tool_call>` XML inside the reasoning block and the turn ended. A direct probe (one
  tool-result turn, 5 to 6 requests each) showed Together returns this malformed form about
  half the time whatever the thinking parameter is (none 3/5, disabled 3/5, enabled 2/5
  malformed), while `:deepinfra` and `:featherless-ai` returned a structured `tool_use`
  6 of 6 times. Check 1 above, S2 and S3 now use `:deepinfra`.
- Added `API_TIMEOUT_MS=300000` to the hf env. The `:deepinfra` check run made 44 tool
  calls, then one router request hung and benchflow's 600 s idle watchdog ended the trial
  (`error: Agent idle for 600s`). That equals Claude Code's default request timeout, so
  Claude Code never got to retry. Not yet exercised in a live run; S2 will show it.
- Check 1 passes: the trial ran to completion with a `result.json` (reward 0, 44 tool
  calls, 2224 s, ended by the idle watchdog as above).
- Check 2 passes: `config.json` `agent_env` has `ANTHROPIC_BASE_URL=https://router.huggingface.co`,
  `ANTHROPIC_MODEL=Qwen/Qwen3.5-9B:deepinfra`, the four tier/subagent variables, and no key
  or token entries.
- Check 3 passes: the token grep over `jobs/s1-check` and `runs` prints nothing.
- Check 4 passes: 14 tool calls completed, 30 failed (all the solver's own Python
  scripts exiting 1, apart from one Read of an oversized file), and no 401/403/404 or
  "model not found" text. The trajectory is at `trajectory/acp_trajectory.jsonl` in this
  benchflow version, not `agent/`.
- Check 5: the repo has no test suite and pytest isn't a dependency. `compileall` is clean,
  and ruff on the touched files reports only rule kinds the files already had (UP042,
  B008, UP045).

### S2. Smoke test: one task, three modes, one trial  [ ]

```sh
OUT=runs/smoke-1-qwen35-9b-$(date +%F)
uv run aip-skillbench run-matrix --config configs/campaign-1.yaml \
  --model Qwen/Qwen3.5-9B:deepinfra --provider hf \
  --agent-env MAX_THINKING_TOKENS=0 \
  --trials 1 --concurrency 3 --out "$OUT" --yes
```

Then inspect each of the three cells' trajectories (`cells/*/*/*/agent/acp_trajectory.jsonl`):

- human-curated: did the solver read the skills and run a multi-step tool loop (more than 3 tool
  calls, no malformed tool-call errors)?
- aip-spec: did it read the pack's SKILL.md and run at least one of the pack's scripts?
- aip-runtime: does the trajectory contain `aip search` and `aip run` output, and at least one
  server pause (`"paused":`) answered with `aip resume`?

Verify: write the three answers plus each cell's status and tool-call count as a note under this
step. Acceptance is *the tool loop works in all three modes*, not reward. If a mode shows the
solver unable to produce well-formed tool calls at all (repeated harness errors, zero tool calls),
record it, switch `--model` to `Qwen/Qwen3-Coder-30B-A3B-Instruct:together` (check the provider
mapping first as in S0.4), rerun, and note which model continues. Commit the note.

### S3. Pilot: five tasks, three modes, five trials  [ ]

```sh
OUT=runs/pilot-5-qwen35-9b-$(date +%F)
tmux new -s bench   # then inside:
uv run aip-skillbench run-matrix --config configs/campaign-5.yaml \
  --model Qwen/Qwen3.5-9B:deepinfra --provider hf \
  --agent-env MAX_THINKING_TOKENS=0 \
  --trials 5 --concurrency 5 --out "$OUT" --yes
```

75 cells. Start at concurrency 5 (hosted rate limits are unknown); if no cell errors with a
429/overloaded message in the first 15 cells, re-launch the same command with `--concurrency 10`
(it resumes). Watch from another terminal with `uv run aip-skillbench matrix-view "$OUT" --watch`.

When done, produce the comparison and save it as `$OUT/REPORT.md`:

1. Per-mode table (pass, fail, error, mean tool calls, mean `agent_execution` from `timing.json`)
   for the pilot, next to the same table for the same five tasks taken from
   `runs/campaign-28-aip-h55-nothink-2026-10-08/summary.jsonl` (Haiku).
2. Per-task passes out of 5 for both solvers, three modes each (the table in "Context" is the
   Haiku side).
3. For every failing aip-spec cell: did the solver deviate from the graph (skipped step, wrong
   order, improvised instead of running a script, wrote output to the wrong place) or execute it
   faithfully and fail anyway? Count the two kinds. This is the drift measurement.
4. For every failing aip-runtime cell: did the server run (pauses present), and where did it stop?
5. Protocol use: count of runtime cells with no `aip run` in the trajectory (expect 0).
6. Errors by message, so infra problems (rate limits, provider errors) are separated from solver
   results.

Verify: `$OUT/REPORT.md` exists with all six sections and `summary.jsonl` has 75 rows. Commit the
report under `reports/` (gitignored, so copy the numbers into the step note instead) and push the
note.

### S4. Decision gate  [ ]

Read S3's report and write the decision under this step, one of:

- **Drift confirmed** (aip-spec dropped clearly below Haiku's 25/25 on these tasks *and* the
  deviation count in S3.3 is non-trivial, *and* aip-runtime held up better than aip-spec):
  schedule the 28-task campaign with this solver, after Track B lands.
- **Too weak** (human, spec and runtime all near zero; failures are tool-loop or comprehension
  failures, not drift): repeat S2 and S3 with `Qwen/Qwen3-Coder-30B-A3B-Instruct:together`, then
  `google/gemma-4-31b` if needed. Duplicate S2 and S3 as S2b/S3b under the new model.
- **Too strong** (spec still at or near 25/25): no drift to measure at this rung; move down to the
  floor is not possible, so record that the procedure alone carries the lift even for a 9B
  solver, which is itself a result, and stop.

Verify: the decision and its two or three supporting numbers are written here. Commit and push.

## Track B (independent of S0 to S4; do on the laptop, where `~/dev/aip` is checked out)

These are the fixes from `runs/campaign-28-aip-h55-nothink-2026-10-08/REPORT.md` section 5. Each
is its own step; tick them here as they land. They must all be in before any 28-task rerun.

### B1. aip runtime: decision resume keeps extra keys; `info` lists all graph inputs  [ ]
`aip/model/steps.py` decision `respond` builds the next state from `payload` plus question
answers only, dropping any other key the client sends; `aip info` shows only the start step's
inputs. Merge non-question keys on resume (as client_task already does) and make `info` list
every input the graph will need. Test: dialogue-parser pack through `aip run` with the four path
keys supplied at the conventions pause reaches `build` without `invalid_input`.

### B2. aip runtime: server-side steps run as the sandbox user  [ ]
Execution steps run as root in the solver's working tree, leaving root-owned outputs the solver
cannot amend (drone-planning-control runtime t2). Run steps as the user that owns the working
directory, or `chown` outputs to it. Test: after a server-executed step writes under a directory
owned by a non-root user, that user can modify the files.

### B3. aip runtime: run file location independent of shell cwd  [ ]
The run file is written relative to the shell cwd, so a solver that `cd`s loses its run. Write it
under a fixed per-run location (home or the server-reported path). Test: `aip run`, `cd /tmp`,
`aip resume` still finds the run.

### B4. harness: Python bootstrap for images below 3.10  [ ]
fix-build-google-auto and suricata-custom-exfil images ship Python 3.9; `aip` uses `match`
statements and `typesafe-sdk` requires 3.10, so runtime mode could not install (10 error cells).
In `_benchflow_patch.py`'s install script, when `python3` is below 3.10, fetch a standalone Python
(e.g. `uv python install 3.12` via a static `uv` binary) and build the venv from it. Test: a
runtime-mode `eval` on suricata-custom-exfil reaches the solver.

### B5. harness: close the pack-on-disk and upstream leak channels in AIP modes  [ ]
After publish, remove `/opt/aip/packs` and make `/opt/aip/catalog` readable by root only (the
server runs as root); have the runtime serve reference files so the solver never needs the pack on
disk (36 of 130 runtime cells read it; 4 read SKILL.md). In aip-spec and aip-runtime modes, remove
`/app/skills` and `/solution`, which upstream benchflow uploads unconditionally. Test: in a
runtime-mode trial, `ls /opt/aip/packs /app/skills /solution` as the agent user all fail.

### B6. packs: five one-line fixes, then re-validate  [ ]
Re-author or patch, then `aip-spec validate`, keeping the `_authoring/` record honest about the
change: mars-clouds-clustering (greedy matching, `file_rad` grouping, all expert images);
travel-planning (always schedule an attraction on travel days); data-to-d3 (legend as HTML
outside the SVG); fix-build-google-auto (no-Python fallback, name the two deliverable files);
drone-planning-control (list `actual_trajectory.npy` in the pack contract). Test: one aip-spec
trial per task passes with Haiku 5.5.

### B7. task defects to report upstream, not fix here  [ ]
civ6-adjacency-optimizer (`/output` root-owned, every mode fails); bike-rebalance (verifier
appears to allow a pre-loaded truck; confirm against `solution/solve.sh` before claiming). Write
both up as issues for the SkillsBench repo and link them here.
