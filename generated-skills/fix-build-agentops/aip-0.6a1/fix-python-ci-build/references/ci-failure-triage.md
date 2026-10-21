# Python CI failure triage playbook

Load this when the error signals don't immediately tell you the root cause, or before
choosing between a code fix and a build-configuration fix.

## How to read a failed job (adapted from analyze-ci)

A good failure analysis states, for each failing job/command:

1. **Root cause**: one sentence naming the file (and line) or config entry at fault.
2. **Error messages**: the exact text (exception type + message, linter code, resolver error).
3. **Test names**: every failing test node id (`tests/x.py::TestY::test_z`), grouped by cause.
4. **Relevant log snippets**: the few lines that prove the cause, not the whole log.

Read from the *first* real error, not the last line: later errors are often cascades
(one `ImportError` in `conftest.py` fails every test module). In GitHub Actions logs the
final `Process completed with exit code N` only says which step failed.

## BugSwarm container facts

- The failing repo lives at `/home/github/build/failed/<repo>/<id>`; the passing version and
  `run_passed.sh` were deleted on purpose: do not look for them.
- `/usr/local/bin/run_failed.sh` (when present) is a **pre-generated** reproduction of the
  failing CI job. Editing `.github/workflows/*.yml` does not change what it runs; fix the files
  its commands read (source, tests, `pyproject.toml`, `setup.py`/`setup.cfg`, `requirements*.txt`,
  `tox.ini`, `pytest.ini`, `uv.lock`, lint configs). Read its text before deciding what to edit.
- Never edit `run_failed.sh` or anything outside the repo: the fix is delivered as
  `patch_{i}.diff` files applied from the repo root (`git apply` / `patch -p1`).
- The container may have no network. Fixes that need new downloads (new dependency versions,
  regenerating `uv.lock`) can fail at verification; prefer fixes that work with what the build
  already installs, and check the reproduction log for what was actually installed.
- `uv` 0.9.x is at `/usr/local/bin/uv`; the job may still install with pip. Use whatever the
  job's own commands use.

## Signal → likely cause → fix

| Signal in log | Usually means | Fix in |
|---|---|---|
| `ModuleNotFoundError: No module named 'x'` for a third-party package | dependency missing from the install set the job uses (extra/group not installed, dep removed) | build config: add it to the dependency list/extra/group the job installs |
| same, for the repo's own package | package not installed / wrong `packages`/`src` layout / missing `__init__.py` / `pythonpath` | config (packaging, `[tool.pytest.ini_options] pythonpath`) or code (`__init__.py`) |
| `ImportError: cannot import name 'X' from 'pkg'` (pkg third-party, frame in site-packages) | the dependency released a breaking version | config: pin `pkg<breaking` (or adapt code if the job installs newest and the pin is impossible) |
| same, `pkg` is the repo's own module | symbol renamed/moved/deleted in the failing commit | code: restore/rename consistently (see `symbol_lookups` in context) |
| `AttributeError`/`TypeError` from repo code | API mismatch between repo modules or with a dependency | code, or pin if dependency changed |
| `AssertionError` in a test | behavior changed in the failing commit | code (make behavior match the test) unless the commit intentionally changed behavior and the test is stale; read the HEAD commit diff |
| `SyntaxError`/`IndentationError` | broken source, or syntax newer than the CI Python (`match`, `X | Y` types, PEP 604 at runtime on 3.9) | code: rewrite for the oldest CI Python version |
| `path:line:col: CODE msg` (ruff/flake8/pylint) | lint violation | code at that line; don't disable rules globally |
| `Would reformat` / `would reformat` | formatter check (black/ruff format) | code: reformat exactly as that formatter would (match its config: line length, quote style) |
| `path:line: error:` (mypy/pyright) | type error | code annotations/logic; avoid blanket `# type: ignore` |
| `'x' not found in markers configuration option` | `--strict-markers` with an unregistered marker | config: register **every** marker the tests use under `markers` — pytest reports only the first missing one, so grep `pytest.mark.` across tests/conftest |
| `unrecognized arguments: --cov` (or other flag) | plugin missing for an `addopts` flag | config: add the plugin to test deps, or drop the flag |
| `async def functions are not natively supported` | pytest-asyncio/anyio plugin missing or `asyncio_mode` not set | config: add plugin / `asyncio_mode = "auto"`; see `pytest-practices.md` |
| `fixture 'x' not found` | fixture removed/renamed, or plugin providing it missing | code (conftest) or config (plugin) |
| `No solution found when resolving` / `ResolutionImpossible` | conflicting constraints or `requires-python` too wide/narrow | config: relax/adjust pins; see `uv-package-manager.md` |
| ``needs to be updated, but `--locked` was provided`` | `uv.lock` out of sync with `pyproject.toml` | config: make `pyproject.toml` match the lock (preferred offline), or regenerate the lock with `uv lock` |
| `requires a different Python` / `requires-python` | package metadata excludes the CI interpreter | config: fix `requires-python` or the pin |
| `command not found` | tool not installed by the job | config: add the tool to the deps the job installs |
| timeout / network errors / missing credentials | environment, not repo | mock at the boundary or skip only network-dependent tests with a clear marker; never delete real tests |

## Errors that hide other errors

pytest stops at collection errors, a failed install stops before tests, and lint steps usually
run before tests. Fixing the first error can expose the next: after each fix, look for sibling
problems of the same kind (other unregistered markers, other stale imports of a renamed symbol,
other uses of a removed API) before re-running.

## Choosing the fix

- Minimal and targeted: change only what the root cause requires; keep unrelated files untouched.
- Fix every independent failure in the log, not just the first one.
- Don't make the build pass by deleting/skipping failing tests, loosening assertions, adding
  `|| true`, or lowering coverage thresholds, unless the failure is purely environmental.
- When a dependency changed under you, a version pin in the config the job actually installs
  from (pyproject dependency/extra/group, `requirements*.txt`, constraints) is usually the
  smallest correct fix.
- Match the oldest Python version in the CI matrix for syntax and stdlib features.
