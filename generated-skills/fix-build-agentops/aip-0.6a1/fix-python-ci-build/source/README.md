# fix-python-ci-build — source material and compilation notes

## Provenance

Compiled on 2026-10-20 from four curated Agent Skills plus the task statement. All copied verbatim here:

| Source | Copied to | Used for |
|---|---|---|
| `analyze-ci/SKILL.md` | `source/analyze-ci/` | Failure-analysis format (root cause, error messages, test names, log snippets) → `assets/diagnose.md`, `references/ci-failure-triage.md` |
| `testing-python/SKILL.md` | `source/testing-python/` | Test/fixture/mocking/async conventions → `references/pytest-practices.md` (verbatim body + a note on applying its project-specific rules to another repo) |
| `temporal-python-testing/SKILL.md` + `resources/*.md` | `source/temporal-python-testing/` | Temporal test patterns → `references/temporal-testing.md` (verbatim, resource paths rewritten) + `references/temporal/*.md` (verbatim) |
| `uv-package-manager/SKILL.md` | `source/uv-package-manager/` | uv/lockfile/dependency knowledge → `references/uv-package-manager.md` (verbatim body + "build-fix notes for uv projects") |
| task `instruction.md` | `source/task-instruction.md` | The three-step contract: analysis + plan in `/home/github/build/failed/failed_reasons.txt`; `patch_{i}.diff` in git/diffutils format at the repo root; apply them |

Environment facts came from the task Dockerfile: BugSwarm cached image (`AgentOps-AI/agentops`),
`/home/github/build/passed` and `/usr/local/bin/run_passed.sh` deleted (so `run_failed.sh` is the
reproduction entry point), `/home/github/build/failed` made world-writable, uv 0.9.22 at
`/usr/local/bin/uv`, Node 22. The task ships no other input files: the repo is inside the image.
So the skill finds everything at runtime and assumes nothing about this particular failure.

## Intent

A downstream agent gets a failed Python CI build and must (1) analyze it and write a plan,
(2) express the fix as diff files, (3) apply them. The four source skills give background
(reading CI failures, pytest, Temporal tests, uv), but none of them reproduces a build, makes
patches, or knows the BugSwarm layout. The skill adds those as deterministic scripts and keeps
the judgment (diagnosis, the fix itself) with the agent, framed by templates and references.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `locate` | execution | Finding the repo (`<failed_root>/<repo>/<id>`), `run_failed.sh`, workflow run steps, package manager, and snapshotting the original files are fixed filesystem rules. The snapshot is the baseline every patch is diffed against, so patches always apply to the *original* repo even after the build has touched files (e.g. `uv.lock`) or after several fix rounds. |
| `reproduce` | execution | Running the job and parsing logs (pytest FAILED/ERROR, collection errors, short and long traceback frames, ruff/flake8, mypy, black/ruff-format, pip/uv resolver and lockfile errors, marker/addopts errors, exit markers) is pattern matching. CI-runner paths such as `/home/runner/work/x/x/...` are mapped back to repo files. |
| `classify` | decision | Code vs build-configuration is a judgment over a fixed label set (`code`, `build_config`, `both`, `unclear`); the task asks for exactly this call. `environment_caused` is a noul guard against "fixing" network/timeout failures in repo code. Thresholds: location 0.6 (a wrong call steers context collection), environment 0.2 (a false "environment" call would excuse a real bug). |
| `collect-context` | execution | Once the location is known, the needed context is deterministic: failing-commit diff (BugSwarm failures come from one commit), code around error lines, definitions/usages of symbols from `cannot import name`/`has no attribute`, whether a missing module is local or declared, config files, `uv lock --check`. |
| `diagnose` | client_task | Root-cause synthesis is generated text; its output is the body of `failed_reasons.txt` in the analyze-ci shape. |
| `write-reasons` | execution | Writing the file to the required path, with the captured signals appended, is fixed. |
| `propose-fix` | client_task | The fix is code the agent writes. It returns structured edits instead of editing files, so the patch files can be written and checked before anything is applied (the task's step 2 → step 3 order). |
| `write-patches` / `apply-patches` | execution | Writing git-format diffs (`diff --git a/ b/`, `/dev/null` for new or deleted files, `\ No newline at end of file`, CRLF kept) and checking them with `git apply --check` against the original files is exactly what hand-written diffs get wrong. Apply restores the originals first, uses `git apply` (with `GIT_CEILING_DIRECTORIES` so a parent repo isn't picked up), writes the content directly if that fails, and confirms the result. |
| `verify` | execution | Same build run as `reproduce`, on the patched tree. |
| `by-result` | router | A passing build ends the run; a failing one goes to one in-place revision round. |
| `revise` | client_task | The remaining fix needs the agent's judgment and an edit/re-run loop, so it edits in place and lists the files it changed. |
| `refresh-patches` | execution | Regenerates every patch from baseline to final tree (so the delivered patches reflect the final state, not the first try), re-checks them, re-runs the build, and appends the revision to `failed_reasons.txt`. |

One script (`scripts/buildfix.py`, stdlib only, Python ≥ 3.6 syntax checked) has a mode per execution
step, so it runs on whatever `python3` the BugSwarm image has without installing anything.
`requires` names `python3` 3.6 plus `bash` (runs the build), `git` (log/show/apply) and `uv`
(`uv lock --check` / version, present at /usr/local/bin/uv in the image).
Scripts write scratch data (baseline, logs, pending contents) to `$TMPDIR/aip-buildfix/<hash>/`.

## Completeness check (source → where it lives)

- analyze-ci "concise failure summary with root cause, error messages, test names, and relevant log snippets" → diagnose template's required sections; `references/ci-failure-triage.md` "How to read a failed job".
- analyze-ci "analyze all failed jobs" → diagnose step 1 and anti-pattern "fixing only the first error"; triage "Errors that hide other errors".
- testing-python (all sections: atomic tests, parametrize, separate tests, asyncio_mode auto/no markers, module-level imports, in-memory FastMCP transport, inline-snapshot commands, function-scoped fixtures, tmp_path, mock at the boundary, don't mock what you own, naming, pytest.raises, run commands, checklist) → `references/pytest-practices.md` verbatim; asyncio rule also an anti-pattern; mock at the boundary in the triage table's environment row.
- temporal-python-testing (philosophy, three test types, resources, quick start, coverage targets ≥80%, principles, references; all four resource files) → `references/temporal-testing.md` + `references/temporal/*.md`, verbatim. Loaded only when code uses temporalio.
- uv-package-manager (concepts, install, venvs, uv run, add/remove/upgrade/lock, python versions, pyproject config, monorepo, CI/CD, Docker, lockfile workflows, cache/parallel/offline, comparisons, workflows, pre-commit, VS Code, troubleshooting, best practices, migration, command reference, resources) → `references/uv-package-manager.md` verbatim; lockfile/`--locked`/resolver/requires-python rows in the triage table; build-fix notes at the top of the reference.
- Task: failed_reasons.txt analysis + plan → diagnose + write-reasons; "identify if errors are in code or build configuration" → classify + diagnose's ERROR LOCATION; patch_{i}.diff in git/diffutils format → write-patches; apply → apply-patches; verification → verify / refresh-patches.

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| analyze-ci's `uv run skills analyze-ci <pr_url|job_url> [--debug]` CLI, `allowed-tools` entry, and examples (mlflow PR/job URLs) | That CLI belongs to the mlflow repo's tooling, calls the Claude API and GitHub with a token, and needs network. None of that exists in the BugSwarm container. Its job (getting the failing log and summarizing it) is done by `reproduce` (local re-run + parser) and `diagnose` (summary format kept). |
| analyze-ci prerequisite "GitHub token via `gh auth token` / `GITHUB_TOKEN`" | Same reason: there is no PR or API access here. |
| testing-python / temporal "write new tests to reach ≥80% coverage" as a *goal* | Kept in the references as background. The task is to repair a failing build, and adding coverage is out of scope (`do_not_use_when`). Lowering coverage thresholds is listed as an anti-pattern. |
| temporal local-setup Docker Compose / Temporal server workflow as a procedure step | Kept verbatim in `references/temporal/local-setup.md`. Not a step because the container has no Docker, and Temporal unit tests use the in-process time-skipping environment. |
| uv installation commands as a step | uv is already installed in the image (`/usr/local/bin/uv`). Kept in the reference. |
