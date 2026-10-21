# Source and provenance — python-ci-build-fix

## Inputs (copied verbatim in this folder)

| Path | Origin | Role in the compiled skill |
|---|---|---|
| `analyze-ci/SKILL.md` | curated skill (mlflow `uv run skills analyze-ci`) | CI-failure analysis intent and output shape → `buildfix.py run/analyze`, failed_reasons template, gotcha on when the original CLI works |
| `testing-python/SKILL.md` | curated skill (FastMCP project test rules) | "Test rules" section; full examples mirrored to `references/testing-python.md` |
| `uv-package-manager/SKILL.md` | curated skill | "uv rules" section and gotchas; full catalogue mirrored to `references/uv-package-manager.md` |
| `temporal-python-testing/SKILL.md` + `resources/*.md` | curated skill | Step 6 Temporal core facts; mirrored to `references/temporal/` (`overview.md` = the SKILL.md with `resources/` prefixes removed so its links resolve as siblings) |

Task context: `inputs/instruction.md` (BugSwarm "fix the failed build" task: analysis in `/home/github/build/failed/failed_reasons.txt`, `patch_{i}.diff` in the repo, then apply) and `inputs/environment/Dockerfile` (BugSwarm cached image `AgentOps-AI-agentops-*`, passed build and `run_passed.sh` removed, uv 0.9.22 at `/usr/local/bin/uv`, Node 22; no extra Python packages guaranteed). `MANIFEST.md` lists no input files: the repository lives only inside the image, so the functional test used agentops-shaped fixture repos under `scratch/` (see below).

## Intent

One coherent unit: take a red Python CI build inside its container to a verified minimal fix with the exact deliverables the task asks for (analysis file, git-format patches, applied changes). The four sources each covered a slice (log analysis, pytest test-writing, uv dependency management, Temporal testing); the compiled skill orders them into a locate → reproduce → diagnose → write-up → fix → verify → patch pipeline.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| 1 Locate (repo discovery, build script, tooling, pytest config, workflow `run:` steps, destructive-line scan, baseline snapshot) | execution | Deterministic filesystem/config inspection; the baseline must be exact for patch generation. |
| 2 Reproduction plan (`run_script_usable`, `repro_command`) | decision | Whether a build script mirrors CI and is safe needs judgment over its text; the answer space is fixed. The destructive-line scan that feeds it is scripted. |
| 3 Reproduce / analyze (run with timeout, log capture, pytest summary/collection/exception/missing-module/lint/type/uv/network signal extraction, location votes) | execution | Regex rules and vote counting over a log are deterministic; replaces analyze-ci's LLM call, which needs network + GitHub token. |
| 4 Diagnosis (`failure_reproduced`, `error_location`, `fix_target`) | decision | Code-vs-config and source-vs-test need reading code and intent; the script's `suggested_location` is input, not the answer. Cost asymmetry stated (editing tests to pass is costly). |
| 5 failed_reasons.txt | client_task | Free text; template fixes the structure (root cause, messages, tests, snippet — analyze-ci's output contract — plus plan). |
| 6 Fix | client_task | Code generation; rules from testing-python / uv / temporal are inline or in references. |
| 7 Verify loop (`compare`: fixed / still failing / new, masked-failure detection, verdict) | execution | Set arithmetic over two analyses; the `exposed` verdict encodes the rule that collection/usage errors mask later failures. |
| 8 Patch (`patch`: diff vs baseline, git headers, new/deleted files, no-EOL marker, stale patch cleanup, apply-in-order proof on a rebuilt base tree) | execution | Fully deterministic and fragile by hand (pre-existing dirty files, format details). |

## Completeness map (source → compiled location)

analyze-ci: purpose/analysis of failed jobs → steps 3–5; prerequisites (`GITHUB_TOKEN` / `gh auth token`), `allowed-tools`, three usage forms (`<pr_url>`, `<job_url> [...]`, `--debug`) → last gotcha; output contract (root cause, error messages, test names, log snippets) → step 5 template and `analyze` fields.

testing-python: atomic/single-behavior tests, naming, parametrize vs separate tests, `asyncio_mode = "auto"` without markers, module-level imports, FastMCP in-memory transport (HTTP only for network features), inline-snapshot + create/fix commands, function-scoped fixtures, `tmp_path`, mock at the boundary with `AsyncMock`, don't mock what you own, `pytest.raises(match=)` incl. async, run commands (`-n auto`, `-x`, file, `-k`, `-m`), checklist → "Test rules" (checklist items are the same rules); code examples → `references/testing-python.md`.

uv-package-manager: `uv run`, `uv sync` (`--frozen`, `--all-extras --dev`, `--offline`), `uv lock` (`--check`, `--upgrade-package`, `--upgrade`, `--verbose`), `uv add/remove` (`--dev`, `--optional`, constraints), `uv tree --outdated`, `uv pip install/show/list/freeze`, `uv export`, `uv python pin`, `uv venv --python`, `uv cache clean`, workspaces and `[tool.uv.sources]`, best practices (commit lockfile, `--frozen` in CI, pin Python, use `uv run`) and troubleshooting → "uv rules" + gotchas; everything else kept verbatim in `references/uv-package-manager.md`.

temporal-python-testing: time-skipping `WorkflowEnvironment`, `Worker`, `ActivityEnvironment`, mocked activities, replay/`Replayer`, determinism rules (`workflow.random()`, `workflow.now()`, I/O via activities), `workflow.get_version()`, ≥80% workflow/activity coverage target → step 6 core facts; when-to-load guidance for each resource → step 6 bullets; full patterns (manual time control, heartbeat/cancellation, signals/queries, retries, CI replay, docker-compose, pytest.ini with `--cov-fail-under=80`, conftest fixtures, Makefile, debugging) → `references/temporal/*`.

Added from task/environment analysis (not in sources): BugSwarm layout and `run_failed.sh`, destructive build scripts, same-container verifier (installed packages vs declared pins), old-interpreter syntax errors, masked failures, no test deletion / `|| true` / workflow-YAML edits as fixes, `uv run` rewriting `uv.lock`, newer pytest-asyncio rejecting custom `event_loop` fixtures.

## Deliberate-drop log (kept only in source/ or references/, not in the body)

- uv: marketing/"what is uv", speed comparisons vs pip/poetry/pip-tools/conda, installation methods (uv is preinstalled in the image), new-project `uv init` walkthroughs, venv activation per OS, Docker/multi-stage builds, VS Code settings, pre-commit config, migration guides, external links — not actionable for repairing an existing repo in a fixed container; still available in `references/uv-package-manager.md`. `uv lock --no-install` dropped as not a meaningful flag for this workflow.
- analyze-ci: example mlflow PR/job URLs — instance-specific.
- temporal: docker-compose server setup, health-check script, Makefile, pre-commit hook, Web UI, history export from production, CI YAML — require a running Temporal server/network; left in `references/temporal/` for the rare case a test needs them. Source links (docs.temporal.io etc.) — background.
- testing-python: FastMCP-specific import examples beyond the rule itself — in the reference.

## Functional test (this session, no fresh agents)

Fixtures under `scratch/` mimicking `/home/github/build/failed/<repo>/<id>` with a git repo, a `.venv`, a GitHub workflow using uv, and a `run_failed.sh`:
- A: code bug (`>=` vs `>`) with a pre-dirty `.gitignore` → `suggested_location: code`, fix, `verdict: green`, patch excludes the pre-existing dirty line, `patch -p1 -R --dry-run` and `git apply --check -R` pass; `--single` mode tested.
- B: build config (`--cov` in addopts without pytest-cov) then a masked third-party import collection error then a masked code failure → `build_config`, then `exposed`, then `green`; patches with modified, new (no trailing newline) and deleted files apply in order.
- C: no-git repo → snapshot fallback patch verified.
- D: `run_failed.sh` with `git clean -fdx`/`git checkout` → flagged in `run_script_destructive_lines`, `run_script_usable=false`, `repro_command=workflow_steps` via `--cmd`; two code bugs, `partial` then `green`; failed_reasons.txt written from the template; run under Python 3.8.
- Synthetic logs: network-only → `environment`; uv `--locked` stale lockfile + ruff + mypy + own-module ImportError → `lockfile_out_of_date`, `lint`, `type_check`, `missing_modules_own`, `both`; `regressed`/`unchanged` verdicts; multi-candidate and missing-root/baseline error paths.
Not possible here: the real AgentOps BugSwarm image (repository not provided as an input file).
