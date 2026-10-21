# Propose the fix as exact edits

Repository root: `{repo_path}` (error location: {error_location}).

Your analysis and plan (also saved as failed_reasons.txt):
```
{analysis}
```

Error signals: {error_signals}

Context collected earlier: {context_report}

## Do

1. Open every file you will change in `{repo_path}` and read the surrounding code; copy
   `old` text from the file itself, never from memory or from the numbered snippets.
2. Implement every step of the FIX PLAN with the smallest change that fixes the root cause.
   Keep the file's style (indentation, quotes, line length the linters enforce).
3. Do **not** edit files yet: the next steps turn your edits into `patch_{{i}}.diff` files,
   check them, then apply them.
4. Never touch `.github/workflows/*` expecting it to change the reproduction, never edit
   files outside the repo, never delete or skip real tests to get green.
   Load `references/pytest-practices.md` for test/fixture/mocking/async changes,
   `references/uv-package-manager.md` for uv/dependency/lockfile changes, and
   `references/temporal-testing.md` when the code uses temporalio.

## Answer with

`edits`: a list of objects, applied in order, paths relative to the repo root:
- `{{"file": "pkg/mod.py", "old": "<exact unique text from the original file>", "new": "<replacement>"}}`
  (`old` must occur exactly once; add surrounding lines to make it unique, or set `"replace_all": true`)
- `{{"file": "path", "content": "<full new file content>"}}` to create or fully rewrite a file
- `{{"file": "path", "delete": true}}` to delete a file

`fix_summary`: 1–3 sentences: what you changed and why it fixes each root cause.
