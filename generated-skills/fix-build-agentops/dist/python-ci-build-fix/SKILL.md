---
name: python-ci-build-fix
description: Diagnose and repair a failed Python CI build (BugSwarm-style reproduced GitHub Actions failure) inside its container - locate the repo and build script, reproduce the failure, classify it as code vs build configuration (pytest, uv/pip dependencies, pyproject), write the analysis to failed_reasons.txt, fix it, emit verified git-style patch_{i}.diff files and apply them. Use when asked to fix a failing build, red CI job, broken pytest run, or uv/lockfile/dependency error in a Python repository.
compatibility: Python >= 3.7 (standard library only) for scripts/buildfix.py; git, bash and tar on PATH. Uses the repo's own interpreter/venv and uv (if present) for the build itself; no extra packages.
---

# Python CI Build Fix

## Trigger When

- A task says a Python repository's build/CI failed and asks to find the errors, write an analysis, produce diff/patch files, and apply them (e.g. repo under `/home/github/build/failed/<repo>/<id>`, notes in `/home/github/build/failed/failed_reasons.txt`).
- A GitHub Actions job, `run_failed.sh`, `pytest`, `uv sync`/`uv run`, ruff or mypy step exits non-zero and the cause is unknown.
- Fixing test failures, collection/import errors, pytest config errors, dependency-resolution or lockfile errors in a pyproject/uv/pip project.
- Writing or repairing pytest tests (including async and Temporal workflow tests) as part of a fix.

## Purpose

Turns "the build is red" into a verified minimal fix. It carries a deterministic pipeline (`scripts/buildfix.py`) that finds the repo and the image's build script, snapshots a baseline, reproduces the failure, extracts failing tests/exceptions/signals and a code-vs-config suggestion, compares runs to tell real progress from regressions and masked failures, and writes `patch_{i}.diff` files that are proven to apply on the original tree. Around it: typed diagnosis decisions, the failed_reasons template, and the pytest/uv/Temporal rules (from the source skills) needed to make the fix correct.

## Before the first script

Check `python3 --version` (>= 3.7), `git --version`, `bash`, `tar`. Name everything missing before continuing; without git the patch step falls back to the baseline snapshot. All commands below run from this skill's folder; `scripts/buildfix.py` writes state to `/tmp/buildfix` (override with `BUILDFIX_STATE`), never into the repo.

## Workflow

Progress:
- [ ] 1 Locate (script) — before any edit
- [ ] 2 Reproduction plan (decision)
- [ ] 3 Reproduce (script)
- [ ] 4 Diagnosis (decision)
- [ ] 5 Write failed_reasons.txt (client task)
- [ ] 6 Fix (client task) + 7 Verify loop (script)
- [ ] 8 Patch files (script) and final check

### 1. Locate — `execution`

```bash
python3 scripts/buildfix.py locate                 # default root /home/github/build/failed
python3 scripts/buildfix.py locate --repo <dir>    # if several candidates or a non-standard layout
```

Output (JSON): `repo`, `is_git`, `config_files`, `package_manager` (uv/poetry/pip), `requires_python`, `own_packages`, `pytest_config` (asyncio_mode, addopts, testpaths), `uses_temporalio`, `venvs_in_repo`, `tools_on_path`, `run_script` (BugSwarm's `/usr/local/bin/run_failed.sh` when present), `run_script_destructive_lines`, `run_script_head`, `workflow_run_steps` (the `run:` commands of the repo's GitHub workflow files), `candidate_logs`, `failed_reasons_path`, `dirty_at_baseline`.
It also records the baseline snapshot that step 8 diffs against, so run it **before editing anything**. Re-running keeps the baseline; `--rebaseline` resets it (only if you have not edited yet).

### 2. Reproduction plan — `decision`

Input: the `locate` output plus the full text of `run_script` (`cat` it) and the workflow steps.

```yaml
run_script_usable:
  type: noul
  instructions: Can the image's build script be run as-is to reproduce the CI failure?
  criteria:
    true: run_script exists, its commands mirror the CI test/lint steps, and it does not reset/clean the git tree (run_script_destructive_lines empty or harmless, e.g. rm -rf of a cache dir).
    false: no run_script, or it would wipe edits (git checkout/reset/clean/stash of the repo), or it only installs and never runs the failing step.
repro_command:
  type: choice
  instructions: Which command reproduces the failing step? Only consider when run_script_usable is false.
  criteria:
    run_script: run_script_usable is true; use the default `run`.
    workflow_steps: rebuild the failing step from workflow_run_steps, using the interpreter the image already has (`<repo>/.venv/bin/python -m pytest ...`, or `uv run --frozen ...`), skipping checkout/setup/install steps that need network.
    test_only: no usable workflow info; run `<python> -m pytest` with the repo's pytest config.
```

A false negative on `run_script_usable` (running a script that wipes the tree) is costly: reconsider any close call that leans true.

### 3. Reproduce — `execution`

```bash
python3 scripts/buildfix.py run --label before                       # run_script
python3 scripts/buildfix.py run --label before --cmd "<command>"     # workflow_steps / test_only
python3 scripts/buildfix.py analyze --log <file> --repo <repo>       # an existing CI log (candidate_logs)
```

`run` runs in the repo (timeout `--timeout`, default 1800 s), saves the log and an analysis JSON (path in `analysis_json`). Fields: `exit_code`, `timed_out`, `pytest_totals`, `failed_tests`, `error_tests`, `collection_errors`, `exceptions`, `missing_modules_own` (the repo's own package → code), `missing_modules_third_party` (→ dependency/config), `cannot_import`, `signals` (each with `hint` code/build_config/environment and the first matching line), `repo_files_in_errors`, `location_votes`, `suggested_location`, `snippets`, `tail`.
Read the log itself around every signal before diagnosing. pytest's short traceback often hides the source frame: rerun one failing test with `--cmd "<python> -m pytest <nodeid> -x --tb=long"` to see it.

### 4. Diagnosis — `decision`

Input: the `before` analysis, the log, and the code at `repo_files_in_errors`. Answer all questions in one pass.

```yaml
failure_reproduced:
  type: noul
  instructions: Does the reproduced run fail for a reason inside the repository (not only network/sandbox noise)?
  criteria:
    true: At least one failing test, collection/import/syntax error, lint/type error, config or resolution error tied to repo files.
    false: Only environment signals (network, DNS, killed/timeout) or the run passed; change the repro command (step 2) before fixing anything.
error_location:
  type: choice
  instructions: Where are the errors that break the build? Start from suggested_location but judge from the evidence.
  criteria:
    code: Source or test code is wrong - assertion failures, AttributeError/TypeError/NameError, syntax unsupported by the image's Python, wrong import of the repo's own module, lint/type errors.
    build_config: pyproject, setup.cfg, requirements, uv.lock, pytest or tool config is wrong - unknown pytest options or markers, missing/mis-pinned dependency, stale lockfile, invalid packaging metadata, coverage gate.
    both: Independent errors of both kinds are present.
    environment: Nothing in the repo is wrong; the failure is infra-only. Report it; do not invent a code change.
fix_target:
  type: choice
  instructions: Which file kind should change for the main error?
  criteria:
    source: Library/application code under own_packages is buggy or incompatible with an installed dependency or the image's Python.
    test: The test itself is wrong (outdated expectation after an intended behavior change, broken fixture, bad import) and the source behavior is correct.
    config: pyproject, setup, requirements, pytest or tool configuration.
    none: environment-only failure.
```

A false positive on `fix_target: test` is costly (editing a test to pass hides a real bug): reconsider any close call that leans `test` and prefer `source` unless the source behavior clearly matches docs or intent.

### 5. Write the analysis — `client_task`

Write `failed_reasons_path` (from `locate`; `/home/github/build/failed/failed_reasons.txt`, outside the repo) using this template — the summary the analyze-ci tool produced (root cause, error messages, test names, log snippets) plus the plan:

```text
Repository: <repo_id>   Commit: <git_head>
Reproduced with: <command>  -> exit <code>, <pytest_totals>

Failing step / tests:
- <nodeid or step>: <error type and message>

Error location: <code|build_config|both|environment>   Fix target: <source|test|config|none>

Root cause:
<1-5 sentences; cite file:line and the decisive log lines>

Relevant log snippet:
<10-30 lines>

Plan:
1. <file> - <exact change and why>
2. ...
Verification: <command that must pass>
```

### 6. Fix — `client_task`

Make the smallest change that removes the root cause, following the plan. Load as needed:
- Editing or adding tests: follow "Test rules" below; examples in `references/testing-python.md`.
- uv/lockfile/dependency or pyproject errors: "uv rules" below; full command catalogue in `references/uv-package-manager.md`.
- `uses_temporalio` is true or failures involve `temporalio`: read `references/temporal/overview.md`, then `references/temporal/unit-testing.md` (WorkflowEnvironment/ActivityEnvironment), `references/temporal/integration-testing.md` (mocked activities, signals, retries), `references/temporal/replay-testing.md` (non-determinism errors) or `references/temporal/local-setup.md` (pytest/coverage config, server) by symptom. Core facts: workflow tests use `WorkflowEnvironment.start_time_skipping()` (sleeps complete instantly) with a `Worker`; activities run under `ActivityEnvironment().run(fn, ...)`; mock activities to isolate workflow logic; replay with `Replayer(workflows=[...]).replay_workflow(history)`, where a non-determinism error means workflow code used `random`/`datetime.now()`/direct I/O (use `workflow.random()`, `workflow.now()`, activities) or changed command order without `workflow.get_version()`; target >= 80% workflow and activity coverage.

### 7. Verify loop — `execution`

```bash
python3 scripts/buildfix.py run --label after1 [--cmd "<same command as before>"]
python3 scripts/buildfix.py compare <before analysis_json> <after1 analysis_json>   # e.g. /tmp/buildfix/runs/before.json
```

`compare` returns `fixed`, `still_failing`, `new_failures`, `signals_cleared/remaining/new`, `before_run_was_blocked`, `build_green`, and `verdict`:
- `green` → go to step 8.
- `exposed` → the blocking error (collection/usage/resolution) is gone and previously masked failures now show; diagnose them (step 4) and repeat. Update failed_reasons.txt with the extra causes.
- `partial` / `unchanged` → re-diagnose; compare the next run against the latest one.
- `regressed` → your edit broke something; fix or revert it.
Also run the full test suite the CI runs if `run_script` only covers part of it.

### 8. Patch files — `execution`

```bash
python3 scripts/buildfix.py patch            # patch_1.diff ... one per changed file, in the repo root
python3 scripts/buildfix.py patch --single   # one patch_1.diff with every file
```

It diffs every file changed since the baseline (pre-existing dirty files are diffed against their baseline copy, so their old changes are excluded), writes git-format diffs (`diff --git` headers with git's a and b prefixes, new and deleted file modes, `\ No newline at end of file`), deletes stale `patch_*.diff`, then rebuilds the base tree in a temp dir, applies the patches in order with `git apply` and checks the result equals your worktree. Require `"ok": true`; on failure read `verification.errors`.
Before running it, inspect `git status`: revert unintended files (`uv.lock` rewritten by `uv run`, generated files, debug edits) so they do not become patches. The worktree already holds the applied change (step 3 of the task); confirm with `git apply --check -R <repo>/patch_1.diff` and a last `run`.

## Test rules (from testing-python)

- Each test atomic: one behavior, name says what broke (`test_login_fails_with_invalid_password`); several asserts only when they verify that one behavior.
- `@pytest.mark.parametrize` for variations of the same concept; separate tests for different behavior.
- Async: check `pytest_config.asyncio_mode`. With `auto`, write plain `async def test_...` and never add `@pytest.mark.asyncio`; with strict/absent mode the marker (and pytest-asyncio installed) is required, so an "async def functions are not natively supported" error means a missing plugin/marker/mode, not a code bug. A session-scoped custom `event_loop` fixture (old conftest pattern) fails on newer pytest-asyncio; set `asyncio_default_fixture_loop_scope` instead.
- All imports at module top, never inside tests.
- Fixtures function-scoped by default; `tmp_path` for files.
- Mock at the boundary (`patch("mymodule.external_client.fetch", new_callable=AsyncMock)`); don't mock what you own.
- Errors: `with pytest.raises(ValueError, match="must be positive"):`.
- FastMCP projects: pass the server to `Client(mcp)` (in-memory transport); HTTP only when testing networking.
- Complex data: `inline-snapshot` (`assert x == snapshot()`; `pytest --inline-snapshot=create` / `=fix`).
- Running: `uv run pytest -n auto` (xdist), `-x` stop at first failure, a single test file, `-k "name"`, `-m "not integration"`.

## uv rules (from uv-package-manager)

- Run with the interpreter the build uses. `uv run` re-syncs (may hit the network and rewrite `uv.lock`/`.venv`): use `uv run --frozen ...` (or `--no-sync`) for checks; `uv sync --frozen` installs exactly the lock (CI commonly runs `uv sync --all-extras --dev` or `--group <name>`); add `--offline` when there is no network and the cache has the wheels.
- `--locked` errors "lockfile needs to be updated" mean pyproject and uv.lock disagree: `uv lock` (or `uv lock --upgrade-package <pkg>`, `--offline` without network), then `uv lock --check`. If the lock cannot be regenerated, make pyproject match the lock instead.
- Dependencies: `uv add "<pkg>>=x,<y"`, `uv add --dev`/`--group test`, `uv remove`, `uv add --optional <extra> <pkg>`; inspect with `uv tree` (`--outdated`), `uv pip list`/`uv pip show`; `uv export --format requirements-txt` for pip-based steps.
- Resolution conflicts: `uv lock --verbose`; cache trouble: `uv cache clean`; wrong interpreter: `uv python pin <v>` / `uv venv --python <v>`.
- Workspaces: root `[tool.uv.workspace] members = [...]`; sources in `[tool.uv.sources]`.

## Gotchas

- The verifier reruns the build in this same container. A dependency added to pyproject is not installed by itself: a fix must pass with the packages present (check `<python> -m pip show <pkg>` or `uv pip show`), or you must install it and keep the declared pin consistent with what is installed. Prefer code compatible with the installed version over pinning.
- The image's Python may be older than the syntax in the code (`X | None` annotations evaluated at runtime on 3.9 → `TypeError: unsupported operand type(s) for |`; `match`; `typing.Self`). Fix in code (`from __future__ import annotations`, `Optional[...]`) rather than changing the interpreter. Compare with `requires_python`.
- BugSwarm images remove the passing build; the real fix is not on disk — do not search for it. Do not `git checkout`/`reset`/`stash` the repo (it destroys the baseline the patches need).
- Never "fix" by deleting or skipping failing tests, adding `|| true`, `continue-on-error`, `-p no:...` hacks, or lowering a coverage gate, unless the diagnosis shows that config itself is the bug. Editing the GitHub workflow YAML does not change what runs in the container.
- Fix every independent error, not just the first: collection or usage errors mask later failures (`verdict: exposed`).
- `patch_{i}.diff` must sit in the repo root and match the final worktree; regenerate with `patch` after any later edit.
- `uv run skills analyze-ci <pr_url|job_url> [--debug]` (source analyze-ci) works only inside a repo that ships that `skills` CLI, with network and a `GITHUB_TOKEN`/`gh auth token`; in the build container use `buildfix.py run/analyze` instead.
