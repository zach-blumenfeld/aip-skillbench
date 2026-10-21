---
name: fix-python-ci-build
description: Diagnose and fix a failed Python CI build (GitHub Actions / BugSwarm image with the repo at /home/github/build/failed/<repo>/<id> and run_failed.sh) — reproduce the job, parse the log (pytest failures, import/collection errors, ruff/flake8/mypy/black, pip/uv/poetry resolver and lockfile errors), classify code vs build-configuration causes, write failed_reasons.txt, emit git-format patch_{i}.diff files, apply them, and re-run until the build passes. Use when a task asks to find why a Python repo's build fails and fix it with diff patches.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Fix a failed Python CI build inside a BugSwarm-style container (failing repo at
  /home/github/build/failed/<repo>/<id>, reproduction script /usr/local/bin/run_failed.sh):
  locate the repo and the job's real command, reproduce the failure and parse the log into
  error signals, classify code vs build-configuration causes, collect targeted context
  (failing-commit diff, code around error lines, config files, uv lock state), write the
  analysis and plan to failed_reasons.txt, turn the planned edits into git-format
  patch_{i}.diff files checked against the original files, apply them, and re-run the build;
  if it still fails, revise in place and regenerate the patches from the original tree.

trigger_when:
  - A task says a Python repository's build/CI failed and asks to find the errors and fix them.
  - The repo is under /home/github/build/failed/ (BugSwarm image) or a run_failed.sh reproduces a failing job.
  - The task asks for failed_reasons.txt and patch_{i}.diff files in git/diffutils diff format.
  - A GitHub Actions job of a Python project (pytest, ruff/flake8, mypy, black, pip/uv/poetry install) fails and the fix must be delivered as patches.

do_not_use_when:
  - The project is not Python or the failure is in a non-Python toolchain only (Node, Java, Go builds).
  - The task is to write a new test suite or feature with no failing build to repair.
  - Only a CI log URL is available and the repository cannot be run locally.

requires:
  interpreter:
    name: python3
    version: "3.6"
  tools:
    - bash
    - git
    - uv

steps:
  - name: locate
    kind: execution
    description: Find the failing repo, the reproduction command (run_failed.sh, else workflow run steps), CI and project facts, and snapshot the original files as the patch baseline.
    inputs:
      - name: failed_root
        type: string
        description: Directory holding the failed build, normally /home/github/build/failed (failed_reasons.txt is written here).
      - name: build_timeout
        type: integer
        description: Seconds allowed for each full build run (1800 is a good default).
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "locate"]
    timeout: 900
    outputs:
      - name: repo_path
        type: string
        description: Absolute path of the failing repository (<failed_root>/<repo>/<id>); patches go here.
      - name: run_command
        type: string
        description: Shell command that reproduces the failing job.
      - name: run_cwd
        type: string
        description: Directory the command runs from.
      - name: ci_summary
        type: object
        description: run_failed.sh path and excerpt, workflow files with their run steps, CI python versions.
      - name: project_summary
        type: object
        description: Package manager, requires-python, config files present, pytest config, git HEAD, tool versions.
      - name: baseline_dir
        type: string
        description: Snapshot of the original repo files that every patch is diffed against.
    inputs_to: reproduce

  - name: reproduce
    kind: execution
    description: Run the failing build, keep the full log, and parse it into error signals, failing tests, an excerpt and the tail.
    inputs:
      - name: repo_path
        type: string
      - name: run_command
        type: string
      - name: run_cwd
        type: string
      - name: build_timeout
        type: integer
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "reproduce"]
    timeout: 7200
    outputs:
      - name: build_exit_code
        type: integer
        description: Exit code of the reproduction run (-9 when killed by the timeout).
      - name: build_reproduced
        type: boolean
        description: True when the run failed (non-zero exit, timeout, or failing-test markers).
      - name: build_log_path
        type: string
        description: Full log of the reproduction run.
      - name: error_signals
        type: list[*]
        description: Parsed errors {kind, file, line, message, log_line}; kinds include pytest-failed, collection-error, lint, type, format, exception, dependency, pytest-usage, traceback-frame.
      - name: failed_tests
        type: list[*]
        description: Failing pytest node ids.
      - name: error_excerpt
        type: string
        description: Log lines around the first errors plus the pytest short summary.
      - name: log_tail
        type: string
        description: Last 120 log lines.
    inputs_to: classify

  - name: classify
    kind: decision
    description: Decide whether the failure lives in code, in build configuration, or both, and whether the environment rather than the repo causes it.
    inputs:
      - name: error_signals
        type: list[*]
      - name: failed_tests
        type: list[*]
      - name: error_excerpt
        type: string
      - name: build_exit_code
        type: integer
      - name: project_summary
        type: object
    questions:
      error_location:
        type: choice
        instructions: >
          Where does the root cause of the failure live? Judge from the first real error, not
          cascades. A missing or broken third-party package (No module named / cannot import name
          from a site-packages module / resolver or lockfile errors / requires-python) is
          build_config; errors raised by the repo's own modules, failing assertions, lint, type and
          format violations on repo files are code. If the exit code is 0 and no failing test or
          error signal appears, answer unclear.
        criteria:
          code: Repo source or test code is wrong — assertion failures, exceptions from repo modules, renamed/missing repo symbols, syntax too new for the CI Python, lint/format/type errors on repo files.
          build_config: How the project is built or its environment assembled is wrong — dependency declarations, version pins, lockfile sync, requires-python, packaging metadata, pytest/ruff/mypy/tox configuration, markers or addopts plugins.
          both: Independent failures of both kinds appear.
          unclear: The build did not fail, timed out, or the log shows no attributable error.
      environment_caused:
        type: noul
        instructions: Is the failure caused by the execution environment rather than repository content — no network access, an external service or credential missing, a job timeout, or a tool absent from the container?
        criteria:
          true: The errors are connection/DNS failures, missing secrets or services, a timeout kill, or a missing system tool, and the repo files look correct.
          false: The errors point at repo files, dependency declarations, or tool configuration.
    thresholds:
      error_location: 0.6
      environment_caused: 0.2
    inputs_to: collect-context

  - name: collect-context
    kind: execution
    description: Collect the context the classification calls for — failing-commit diff, code around error lines, symbol and missing-module lookups, config files, uv lock check.
    inputs:
      - name: repo_path
        type: string
      - name: error_location
        type: string
      - name: error_signals
        type: list[*]
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "context"]
    timeout: 600
    outputs:
      - name: context_report
        type: object
        description: recent_commits, head_commit_stat, head_commit_diff, git_status, code_snippets, symbol_lookups, missing_modules, config_files, uv_lock_check, tools (keys present per error_location).
    inputs_to: diagnose

  - name: diagnose
    kind: client_task
    description: Write the failure analysis and fix plan (root causes, error messages, failing tests, log evidence, file-by-file plan).
    inputs:
      - name: run_command
        type: string
      - name: build_exit_code
        type: integer
      - name: error_location
        type: string
      - name: environment_caused
        type: boolean
      - name: failed_tests
        type: list[*]
      - name: error_signals
        type: list[*]
      - name: error_excerpt
        type: string
      - name: log_tail
        type: string
      - name: context_report
        type: object
      - name: ci_summary
        type: object
      - name: project_summary
        type: object
    template: assets/diagnose.md
    references:
      - path: references/ci-failure-triage.md
        description: Signal-to-cause-to-fix table for Python CI failures, BugSwarm container facts, and rules for choosing a minimal fix. Load when the cause or the code-vs-config call is not obvious.
      - path: references/uv-package-manager.md
        description: uv commands, lockfiles, dependency groups, requires-python, CI usage. Load for uv projects or resolver/lockfile errors.
      - path: references/pytest-practices.md
        description: pytest conventions (fixtures, parametrize, mocking at the boundary, async tests, asyncio_mode, markers). Load when tests or pytest config are involved.
      - path: references/temporal-testing.md
        description: Testing Temporal workflows/activities (time-skipping WorkflowEnvironment, ActivityEnvironment, mocked activities, replay/determinism) with per-topic files under references/temporal/. Load only when the failing code uses temporalio.
    outputs:
      - name: analysis
        type: string
        description: The analysis and plan, in the template's section format.
    inputs_to: write-reasons

  - name: write-reasons
    kind: execution
    description: Write the analysis plus the captured error signals to <failed_root>/failed_reasons.txt.
    inputs:
      - name: failed_root
        type: string
      - name: analysis
        type: string
      - name: run_command
        type: string
      - name: build_exit_code
        type: integer
      - name: error_signals
        type: list[*]
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "reasons"]
    timeout: 60
    outputs:
      - name: reasons_path
        type: string
        description: Path of failed_reasons.txt.
    inputs_to: propose-fix

  - name: propose-fix
    kind: client_task
    description: Turn the fix plan into exact edits (old/new replacements, full rewrites, deletions) without touching the files yet.
    inputs:
      - name: repo_path
        type: string
      - name: analysis
        type: string
      - name: error_location
        type: string
      - name: error_signals
        type: list[*]
      - name: context_report
        type: object
    template: assets/propose-fix.md
    references:
      - path: references/ci-failure-triage.md
        description: Rules for minimal, honest fixes (no skipping tests, pin vs adapt, oldest CI Python). Load before choosing between alternatives.
      - path: references/pytest-practices.md
        description: How to write or repair tests, fixtures, mocks and async tests correctly. Load when editing tests or conftest.
      - path: references/uv-package-manager.md
        description: pyproject/uv.lock/dependency-group syntax. Load when editing dependencies or lockfiles.
      - path: references/temporal-testing.md
        description: Temporal workflow/activity test patterns. Load only when the code uses temporalio.
    outputs:
      - name: edits
        type: list[*]
        description: Ordered edits — {file, old, new[, replace_all]}, {file, content}, or {file, delete:true}; paths relative to the repo root.
      - name: fix_summary
        type: string
        description: What changed and why it fixes each root cause.
    inputs_to: write-patches

  - name: write-patches
    kind: execution
    description: Compute each edited file's new content from the original, write one git-format patch_{i}.diff per file at the repo root, and git-apply-check them against the original files.
    inputs:
      - name: repo_path
        type: string
      - name: baseline_dir
        type: string
      - name: edits
        type: list[*]
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "patch"]
    timeout: 300
    outputs:
      - name: patch_files
        type: list[*]
        description: Absolute paths of the patch_{i}.diff files written.
      - name: edited_files
        type: list[*]
        description: Repo-relative files the patches change.
      - name: edit_errors
        type: list[*]
        description: Edits that could not be applied (old text not found or not unique, bad path, no-op).
      - name: patch_check
        type: string
        description: Result of git apply --check against the original files.
    inputs_to: apply-patches

  - name: apply-patches
    kind: execution
    description: Apply the patch files to the repo with git apply (restoring originals first; direct write as fallback) and confirm the result matches the intended edits.
    inputs:
      - name: repo_path
        type: string
      - name: baseline_dir
        type: string
      - name: patch_files
        type: list[*]
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "apply"]
    timeout: 300
    outputs:
      - name: applied_files
        type: list[*]
        description: Files changed in the repo.
      - name: apply_method
        type: string
        description: git apply and/or direct write.
      - name: apply_errors
        type: list[*]
        description: Problems while applying.
    inputs_to: verify

  - name: verify
    kind: execution
    description: Re-run the build command on the patched repo and parse the new log.
    inputs:
      - name: repo_path
        type: string
      - name: run_command
        type: string
      - name: run_cwd
        type: string
      - name: build_timeout
        type: integer
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "verify"]
    timeout: 7200
    outputs:
      - name: build_passed
        type: boolean
        description: True when the build exits 0 within the timeout.
      - name: verify_exit_code
        type: integer
      - name: verify_log_path
        type: string
      - name: verify_signals
        type: list[*]
      - name: verify_failed_tests
        type: list[*]
      - name: verify_log_tail
        type: string
    inputs_to: by-result

  - name: by-result
    kind: router
    description: A passing build is done; a failing one goes to an in-place revision round.
    branch_on: build_passed
    branches:
      "true": end
      "false": revise

  - name: revise
    kind: client_task
    description: Fix what is still failing directly in the repo, re-running the build until it passes, and list every file changed.
    inputs:
      - name: repo_path
        type: string
      - name: run_command
        type: string
      - name: run_cwd
        type: string
      - name: analysis
        type: string
      - name: fix_summary
        type: string
      - name: edit_errors
        type: list[*]
      - name: apply_errors
        type: list[*]
      - name: verify_failed_tests
        type: list[*]
      - name: verify_signals
        type: list[*]
      - name: verify_log_tail
        type: string
    template: assets/revise.md
    references:
      - path: references/ci-failure-triage.md
        description: Signal-to-cause-to-fix table and BugSwarm facts. Load when the remaining failure's cause is unclear.
      - path: references/pytest-practices.md
        description: Test, fixture, mocking and async-test conventions. Load when the remaining failure is in tests or pytest config.
      - path: references/uv-package-manager.md
        description: uv dependency/lockfile handling. Load for resolver, lockfile, or install errors.
      - path: references/temporal-testing.md
        description: Temporal testing patterns. Load only when the code uses temporalio.
    outputs:
      - name: revised_files
        type: list[*]
        description: Repo-relative paths changed, created or deleted in this round.
      - name: revision_notes
        type: string
        description: What was still wrong and what changed.
    inputs_to: refresh-patches

  - name: refresh-patches
    kind: execution
    description: Regenerate every patch_{i}.diff from the original files to the final working tree, check them, re-run the build, and append the revision to failed_reasons.txt.
    inputs:
      - name: repo_path
        type: string
      - name: baseline_dir
        type: string
      - name: edited_files
        type: list[*]
      - name: revised_files
        type: list[*]
      - name: revision_notes
        type: string
      - name: reasons_path
        type: string
      - name: run_command
        type: string
      - name: run_cwd
        type: string
      - name: build_timeout
        type: integer
    script: scripts/buildfix.py
    command: ["python3", "buildfix.py", "refresh"]
    timeout: 7200
    outputs:
      - name: final_patch_files
        type: list[*]
        description: The regenerated patch files (these replace patch_files).
      - name: final_patch_check
        type: string
      - name: final_build_passed
        type: boolean
      - name: final_log_tail
        type: string
    inputs_to: end

  - name: end
    kind: end
    description: failed_reasons.txt written, patch_{i}.diff files at the repo root (regenerated by refresh-patches on the revision path), fixes applied to the repo.
    inputs:
      - name: repo_path
        type: string
      - name: reasons_path
        type: string
      - name: patch_files
        type: list[*]
      - name: fix_summary
        type: string

anti_patterns:
  - Editing .github/workflows/*.yml to fix a BugSwarm reproduction — run_failed.sh is pre-generated and won't see it; fix the files its commands read.
  - Making the build green by deleting or skipping failing tests, loosening assertions, adding `|| true`, or lowering coverage thresholds.
  - Fixing only the first error when the log shows several independent failures.
  - Hand-writing diff files or diffing against already-modified files — patches must apply with `git apply`/`patch -p1` from the repo root to the original repo; let write-patches/refresh-patches generate them.
  - Editing run_failed.sh or anything outside the repo, or writing patches/notes to /tmp instead of the paths the task names.
  - Looking for the passing version or run_passed.sh — they were removed on purpose.
  - Using syntax or stdlib features newer than the oldest Python in the CI matrix.
  - Upgrading or adding dependencies that need network downloads when a pin or a code change within what the build already installs fixes the error.
  - Adding @pytest.mark.asyncio where the repo sets asyncio_mode = "auto", or omitting async support where it doesn't.
```
