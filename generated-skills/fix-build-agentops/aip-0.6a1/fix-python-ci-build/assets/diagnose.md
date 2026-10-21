# Diagnose the failed build: write the analysis and plan

The failing CI job was re-run in this container with `{run_command}` (exit code {build_exit_code}).
The analysis you write becomes `failed_reasons.txt`, the notes you will fix from in the next step.

Classification so far: error location = **{error_location}**; environment-caused = {environment_caused}.

Failing tests: {failed_tests}

Error signals (parsed from the log; `file` is repo-relative when the file is in the repo):
{error_signals}

Log excerpt around the errors:
```
{error_excerpt}
```

Log tail:
```
{log_tail}
```

Collected context (HEAD commit diff, code snippets around the error lines, symbol lookups,
config files, uv lock check):
{context_report}

CI facts: {ci_summary}
Project facts: {project_summary}

## Do

1. Find the first real error and every *independent* failure (one broken import in a
   conftest cascades into many test errors; count it once). Use the HEAD commit diff: the
   failing commit usually introduced the break.
2. Open the files named in the signals in the repo if the snippets are not enough. Check what
   `run_failed.sh` actually executes (ci_summary.run_script_excerpt): edits to
   `.github/workflows/*.yml` do not change it.
3. Decide, per failure, whether the fix belongs in code or in build configuration, and what
   the smallest correct change is. Load `references/ci-failure-triage.md` if unsure.
4. If the build did not fail (exit 0, no failing tests), say so, look for what the job would
   still fail on (the log may hide a failure behind `|| true`), and plan only well-evidenced changes.

## Answer with

`analysis`: plain text with exactly these sections:

```
FAILING COMMAND: <command, exit code>
ERROR LOCATION: code | build configuration | both  (+ one line why)
ROOT CAUSES:
  1. <file[:line] or config entry> — <cause> — evidence: "<exact error message>"
  ...
FAILING TESTS: <node ids grouped by root cause, or "none (lint/build step)">
RELEVANT LOG LINES:
  <the few lines that prove each cause>
FIX PLAN:
  1. <repo-relative file> — <precise change> — fixes root cause N
  ...
VERIFICATION: <command to re-run and what passing looks like>
```
