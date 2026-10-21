#!/usr/bin/env python3
"""buildfix.py - locate, reproduce, analyze, verify and patch a failed Python CI build.

Requires: Python >= 3.7, standard library only. Optional tools it calls when
present: git (strongly recommended), bash, uv. No third-party packages.

Subcommands (all print JSON to stdout; human notes go to stderr):
  locate   [--root DIR] [--repo DIR]      find the repo, build script, tooling; record a baseline
  run      [--repo DIR] [--cmd CMD] [--label L] [--timeout S]
                                          run the build (default: the image's run_failed.sh),
                                          save the log, analyze it
  analyze  --log FILE [--repo DIR]        extract failures and classify signals from a log
  compare  BEFORE.json AFTER.json         fixed / still failing / new failures between two runs
  patch    [--repo DIR] [--single]        write patch_{i}.diff for every change since the
                                          baseline and prove they apply cleanly

State (baseline snapshot, logs, analyses) lives in $BUILDFIX_STATE or /tmp/buildfix,
never inside the repository.
"""
from __future__ import print_function

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

STATE = os.environ.get("BUILDFIX_STATE", "/tmp/buildfix")
DEFAULT_ROOT = "/home/github/build/failed"
RUN_SCRIPT_CANDIDATES = ["/usr/local/bin/run_failed.sh", "/home/github/run_failed.sh"]
SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache",
             ".mypy_cache", ".ruff_cache", ".tox", ".nox", "build", "dist", ".eggs", "htmlcov",
             ".coverage_html", "site-packages"}
NOISE_FILE_RE = re.compile(r"(^|/)(patch_\d+\.diff|failed_reasons\.txt|\.coverage(\..*)?|coverage\.xml"
                           r"|.*\.pyc|.*\.egg-info(/.*)?|\.DS_Store)$")
DESTRUCTIVE_RE = re.compile(r"\bgit\s+(clean|reset|checkout|stash|restore)\b|\brm\s+-rf\b")


def eprint(*a):
    print(*a, file=sys.stderr)


def sh(cmd, cwd=None, timeout=120):
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=timeout,
                           shell=isinstance(cmd, str))
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def read(path, limit=None):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(limit) if limit else f.read()
    except OSError:
        return ""


def is_git(repo):
    rc, out, _ = sh(["git", "rev-parse", "--show-toplevel"], cwd=repo)
    return rc == 0 and os.path.realpath(out.strip()) == os.path.realpath(repo)


def sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def dump(obj):
    print(json.dumps(obj, indent=2, sort_keys=False))


# --------------------------------------------------------------------------- locate

def find_repos(root):
    found = []
    if not os.path.isdir(root):
        return found
    base_depth = root.rstrip("/").count("/")
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip("/").count("/") - base_depth
        markers = {".git", "pyproject.toml", "setup.py", "setup.cfg"}
        if markers & (set(dirnames) | set(filenames)):
            found.append(dirpath)
            dirnames[:] = []  # do not descend into a repo
            continue
        if depth >= 4:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    return found


def toml_value(text, section, key):
    """Tiny TOML reader for `key = value` inside [section]; enough for config discovery."""
    m = re.search(r"^\[" + re.escape(section) + r"\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not m:
        return None
    k = re.search(r"^\s*" + re.escape(key) + r"\s*=\s*(.+)$", m.group(1), re.M)
    return k.group(1).strip().strip('"\'') if k else None


def own_packages(repo):
    pkgs = set()
    text = read(os.path.join(repo, "pyproject.toml"))
    name = toml_value(text, "project", "name") or toml_value(text, "tool.poetry", "name")
    if name:
        pkgs.add(name.replace("-", "_").lower())
    for base in (repo, os.path.join(repo, "src")):
        if not os.path.isdir(base):
            continue
        for d in os.listdir(base):
            if d in SKIP_DIRS or d.startswith(".") or d in ("tests", "test", "docs", "examples"):
                continue
            if os.path.isfile(os.path.join(base, d, "__init__.py")):
                pkgs.add(d.lower())
    return sorted(pkgs)


def workflow_runs(repo):
    wf_dir = os.path.join(repo, ".github", "workflows")
    out = {}
    if not os.path.isdir(wf_dir):
        return out
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        lines = read(os.path.join(wf_dir, fn)).splitlines()
        cmds = []
        i = 0
        while i < len(lines):
            m = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[i])
            if m:
                indent, val = len(m.group(1)), m.group(2).strip()
                if val in ("|", ">", "|-", ">-", ""):
                    block = []
                    i += 1
                    while i < len(lines) and (not lines[i].strip() or
                                              len(lines[i]) - len(lines[i].lstrip()) > indent):
                        if lines[i].strip():
                            block.append(lines[i].strip())
                        i += 1
                    cmds.append(" && ".join(block))
                    continue
                cmds.append(val)
            i += 1
        out[fn] = cmds
    return out


def pytest_config(repo):
    cfg = {}
    text = read(os.path.join(repo, "pyproject.toml"))
    for key in ("asyncio_mode", "testpaths", "addopts", "asyncio_default_fixture_loop_scope",
                "minversion", "markers"):
        v = toml_value(text, "tool.pytest.ini_options", key)
        if v is not None:
            cfg[key] = v
    for ini, sec in (("pytest.ini", "pytest"), ("setup.cfg", "tool:pytest"), ("tox.ini", "pytest")):
        t = read(os.path.join(repo, ini))
        m = re.search(r"^\[" + re.escape(sec) + r"\]\s*$(.*?)(?=^\[|\Z)", t, re.M | re.S)
        if m:
            cfg["_file"] = ini
            for line in m.group(1).splitlines():
                kv = re.match(r"^\s*(asyncio_mode|testpaths|addopts|minversion)\s*=\s*(.+)$", line)
                if kv:
                    cfg[kv.group(1)] = kv.group(2).strip()
    if text and "tool.pytest.ini_options" in text:
        cfg.setdefault("_file", "pyproject.toml")
    return cfg


def take_baseline(repo, git):
    """Snapshot what the repo looks like before any edit, so `patch` diffs only our changes."""
    base = os.path.join(STATE, "baseline")
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(os.path.join(base, "files"))
    meta = {"repo": repo, "git": git, "time": time.time(), "dirty": {}, "manifest": {}}
    if git:
        rc, out, _ = sh(["git", "status", "--porcelain", "-uall", "-z"], cwd=repo)
        meta["head"] = sh(["git", "rev-parse", "HEAD"], cwd=repo)[1].strip()
        entries = [e for e in out.split("\0") if e]
        for e in entries:
            path = e[3:]
            full = os.path.join(repo, path)
            if os.path.isfile(full):
                dst = os.path.join(base, "files", path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(full, dst)
                meta["dirty"][path] = {"status": e[:2], "sha": sha(full)}
            else:
                meta["dirty"][path] = {"status": e[:2], "sha": None}
    else:
        for dirpath, dirnames, filenames in os.walk(repo):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, repo)
                if os.path.getsize(full) > 2000000 or not os.path.isfile(full):
                    continue
                dst = os.path.join(base, "files", rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(full, dst)
                meta["manifest"][rel] = sha(full)
    with open(os.path.join(base, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    return meta


def cmd_locate(args):
    os.makedirs(STATE, exist_ok=True)
    repos = [os.path.abspath(args.repo)] if args.repo else find_repos(args.root)
    result = {"root": args.root, "candidates": repos, "state_dir": STATE}
    if not repos:
        result["error"] = "no repository found under %s; pass --repo" % args.root
        dump(result)
        return 2
    if len(repos) > 1 and not args.repo:
        result["note"] = "several candidates; re-run with --repo <dir> for the one the task names"
    repo = repos[0]
    git = is_git(repo)
    files = sorted(f for f in os.listdir(repo))
    configs = [f for f in ("pyproject.toml", "uv.lock", "poetry.lock", "setup.py", "setup.cfg",
                           "requirements.txt", "requirements-dev.txt", "tox.ini", "noxfile.py",
                           "pytest.ini", "conftest.py", ".python-version", "Makefile",
                           ".pre-commit-config.yaml", "ruff.toml", ".ruff.toml", "mypy.ini",
                           ".flake8", "Pipfile") if f in files]
    run_script = next((p for p in RUN_SCRIPT_CANDIDATES if os.path.isfile(p)), None)
    if not run_script:
        for d in (os.path.dirname(args.root.rstrip("/")), args.root, repo):
            cand = os.path.join(d, "run_failed.sh")
            if os.path.isfile(cand):
                run_script = cand
                break
    run_text = read(run_script) if run_script else ""
    logs = []
    for d in (args.root, os.path.dirname(args.root.rstrip("/"))):
        if os.path.isdir(d):
            logs += [os.path.join(d, f) for f in os.listdir(d) if f.endswith((".log", ".txt"))]
    tools = {}
    for t in ("uv", "python3", "python", "pip", "poetry", "pytest", "ruff", "git"):
        p = shutil.which(t)
        if p:
            tools[t] = p
    venvs = [v for v in (".venv", "venv", "env") if os.path.isfile(os.path.join(repo, v, "bin", "python"))]
    pyver = sh([sys.executable, "--version"])[1].strip() or sys.version.split()[0]
    pyproject = read(os.path.join(repo, "pyproject.toml"))
    result.update({
        "repo": repo,
        "repo_id": os.path.relpath(repo, args.root) if repo.startswith(args.root) else repo,
        "is_git": git,
        "config_files": configs,
        "package_manager": ("uv" if "uv.lock" in files or "[tool.uv" in pyproject or
                            re.search(r"\buv (sync|run|pip)\b", run_text + json.dumps(workflow_runs(repo))) else
                            "poetry" if "poetry.lock" in files or "[tool.poetry" in pyproject else
                            "pip"),
        "requires_python": toml_value(pyproject, "project", "requires-python"),
        "build_backend": toml_value(pyproject, "build-system", "build-backend"),
        "own_packages": own_packages(repo),
        "pytest_config": pytest_config(repo),
        "uses_temporalio": "temporalio" in pyproject or "temporalio" in read(os.path.join(repo, "requirements.txt")),
        "venvs_in_repo": venvs,
        "tools_on_path": tools,
        "python_running_this": pyver,
        "run_script": run_script,
        "run_script_destructive_lines": [l.strip() for l in run_text.splitlines() if DESTRUCTIVE_RE.search(l)],
        "run_script_head": run_text.splitlines()[:80],
        "workflow_run_steps": workflow_runs(repo),
        "candidate_logs": logs,
        "existing_outputs": [f for f in files if re.match(r"patch_\d+\.diff$", f)] +
                            [p for p in [os.path.join(args.root, "failed_reasons.txt")] if os.path.isfile(p)],
        "failed_reasons_path": os.path.join(args.root, "failed_reasons.txt"),
    })
    with open(os.path.join(STATE, "locate.json"), "w") as f:
        json.dump({"repo": repo, "run_script": run_script}, f)
    if git:
        result["git_head"] = sh(["git", "log", "-1", "--format=%H %s"], cwd=repo)[1].strip()
    bl = os.path.join(STATE, "baseline", "meta.json")
    if os.path.isfile(bl) and not args.rebaseline and json.load(open(bl)).get("repo") == repo:
        meta = json.load(open(bl))
        result["baseline"] = "kept existing baseline from %s (use --rebaseline to reset)" % time.ctime(meta["time"])
    else:
        meta = take_baseline(repo, git)
        result["baseline"] = "recorded"
    result["dirty_at_baseline"] = sorted(meta.get("dirty", {}))
    dump(result)
    return 0


# --------------------------------------------------------------------------- analyze

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TS_PREFIX = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z\s?")

SIGNALS = [
    # (kind, location_hint, regex)
    ("lockfile_out_of_date", "build_config",
     r"lockfile .* needs to be updated|uv\.lock.*(out of date|needs to be updated)|poetry\.lock.*(not consistent|out of date)|pyproject\.toml changed significantly"),
    ("dependency_resolution", "build_config",
     r"No solution found when resolving|ResolutionImpossible|Could not find a version that satisfies|conflicting dependencies|Because .* depends on .* and .* we can conclude"),
    ("build_backend_failure", "build_config",
     r"subprocess-exited-with-error|Failed to build |error: Failed to (build|prepare)|Backend subprocess exited|invalid pyproject\.toml|TOMLDecodeError|ValueError: .*(hatch|setuptools)|Multiple top-level packages discovered"),
    ("pyproject_invalid", "build_config",
     r"pyproject\.toml.*(invalid|error|failed to parse)|TOML parse error|`project\.\S+` must be"),
    ("command_not_found", "build_config", r": command not found|No such file or directory: '(uv|pytest|ruff|poetry)'|error: Failed to spawn"),
    ("pytest_usage_error", "build_config",
     r"pytest: error:|ERROR: usage:|unrecognized arguments:|ERROR: file or directory not found:|no tests ran|PytestConfigWarning|'\S+' not found in `markers` configuration option"),
    ("async_plugin_missing", "build_config",
     r"async def functions are not natively supported|PytestUnhandledCoroutineWarning|fixture 'event_loop' not found|ScopeMismatch"),
    ("coverage_threshold", "build_config", r"Required test coverage of [\d.]+% not reached|FAIL Required test coverage"),
    ("network", "environment",
     r"Temporary failure in name resolution|Could not resolve host|Max retries exceeded|Connection refused|Network is unreachable|Failed to fetch|ConnectTimeout|ReadTimeout|SSL: CERTIFICATE_VERIFY_FAILED|Failed to download"),
    ("timeout_killed", "environment", r"\bKilled\b|exceeded the maximum execution time|Terminated|Timeout >[\d.]+s"),
    ("syntax_error", "code", r"\b(SyntaxError|IndentationError|TabError)\b"),
    ("import_error", "code_or_build", r"\b(ModuleNotFoundError|ImportError)\b"),
    ("attribute_or_type_error", "code", r"\b(AttributeError|TypeError|NameError|KeyError|ValueError)\b: "),
    ("assertion_failure", "code", r"^E\s+(assert|AssertionError)|\bAssertionError\b"),
    ("lint", "code", r"^\S+\.py:\d+:\d+: [A-Z]{1,3}\d{2,4}\b|Found \d+ errors?\.|would reformat |Would reformat:|--> \S+\.py:\d+:\d+"),
    ("type_check", "code", r"^\S+\.py:\d+: error: .*\[[a-z-]+\]$|Found \d+ errors? in \d+ files?"),
]
SIGNAL_RES = [(k, h, re.compile(r, re.M | re.I if k not in ("lint", "type_check", "assertion_failure") else re.M))
              for k, h, r in SIGNALS]

PYTEST_SUMMARY = re.compile(r"^(FAILED|ERROR)\s+(\S+?)(?:\s+-\s+(.*))?$")
PYTEST_TOTALS = re.compile(r"^(?:=+ )?((?:\d+ (?:failed|passed|errors?|skipped|deselected|xfailed|xpassed|warnings?)|no tests ran).*?) in [\d.]+s")
COLLECT_ERR = re.compile(r"^_+ ERROR collecting (\S+) _+$")
EXC_LINE = re.compile(r"^(?:E\s+)?([A-Za-z_][\w.]*(?:Error|Exception|Exit|Warning|Interrupt))(?::\s*(.*))?$")
NO_MODULE = re.compile(r"No module named '([^']+)'")
CANNOT_IMPORT = re.compile(r"cannot import name '([^']+)' from '([^']+)'")
TB_FILE = re.compile(r'File "([^"]+)", line (\d+)')
PATH_LINE = re.compile(r"(?:^|\s|-->\s)((?:[\w.\-]+/)*[\w.\-]+\.py):(\d+)")
EXIT_LINE = re.compile(r"(?:Process completed with exit code|exit code|exited with code|returned non-zero exit status) (\d+)", re.I)


def norm_lines(text):
    return [TS_PREFIX.sub("", ANSI.sub("", l)).rstrip() for l in text.splitlines()]


def analyze_text(text, repo=None):
    lines = norm_lines(text)
    own = own_packages(repo) if repo and os.path.isdir(repo) else []
    failed, errors, totals, collect = [], [], [], []
    exceptions, missing_modules, bad_imports = {}, {}, {}
    signals = {}
    files = {}
    for idx, line in enumerate(lines):
        m = PYTEST_SUMMARY.match(line)
        if m and ("::" in m.group(2) or m.group(2).endswith(".py")):
            (failed if m.group(1) == "FAILED" else errors).append(
                {"test": m.group(2), "reason": (m.group(3) or "").strip()[:300]})
        m = PYTEST_TOTALS.match(line)
        if m:
            totals.append(m.group(1))
        m = COLLECT_ERR.match(line)
        if m:
            collect.append(m.group(1))
        m = EXC_LINE.match(line.strip())
        if m and not m.group(1).endswith("Warning"):
            key = (m.group(1) + ": " + (m.group(2) or "")).strip()[:300]
            if key not in exceptions:
                exceptions[key] = {"count": 0, "first_line": idx + 1}
            exceptions[key]["count"] += 1
        for mm in NO_MODULE.finditer(line):
            missing_modules.setdefault(mm.group(1), idx + 1)
        for mm in CANNOT_IMPORT.finditer(line):
            bad_imports.setdefault("%s from %s" % (mm.group(1), mm.group(2)), idx + 1)
        for rx in (TB_FILE, PATH_LINE):
            for mm in rx.finditer(line):
                p = mm.group(1)
                if "site-packages" in p or "/lib/python" in p or p.startswith("<"):
                    continue
                rel = p
                if repo and os.path.isabs(p) and os.path.realpath(p).startswith(os.path.realpath(repo) + os.sep):
                    rel = os.path.relpath(os.path.realpath(p), os.path.realpath(repo))
                if repo and not os.path.isabs(rel) and not os.path.isfile(os.path.join(repo, rel)):
                    continue
                files.setdefault(rel, set()).add(int(mm.group(2)))
    for kind, hint, rx in SIGNAL_RES:
        hits = [i + 1 for i, l in enumerate(lines) if rx.search(l)]
        if hits:
            signals[kind] = {"hint": hint, "count": len(hits), "first_line": hits[0],
                             "example": lines[hits[0] - 1][:240]}
    # split missing modules into repo-own vs third-party
    own_missing = {m: l for m, l in missing_modules.items() if m.split(".")[0].lower() in own}
    third_missing = {m: l for m, l in missing_modules.items() if m not in own_missing}
    exit_codes = [int(m.group(1)) for m in (EXIT_LINE.search(l) for l in lines) if m]

    # deterministic location suggestion (the agent confirms it as the `error_location` decision)
    votes = {"code": 0, "build_config": 0, "environment": 0}
    for kind, s in signals.items():
        if s["hint"] in votes:
            votes[s["hint"]] += 1
    if third_missing:
        votes["build_config"] += 2
    if own_missing or bad_imports:
        votes["code"] += 2
    if failed or [e for e in errors if e["test"] not in collect]:
        votes["code"] += 1
    nonzero = [k for k, v in votes.items() if v]
    if not nonzero:
        suggestion = "unknown"
    elif nonzero == ["environment"]:
        suggestion = "environment"
    elif votes["code"] and votes["build_config"]:
        suggestion = "both"
    else:
        suggestion = max(("code", "build_config"), key=lambda k: votes[k]) if (votes["code"] or votes["build_config"]) else "environment"

    # error snippets: context windows around the first few hard errors
    anchors = sorted({s["first_line"] for s in signals.values()} |
                     {v["first_line"] for v in list(exceptions.values())[:5]})[:8]
    snippets = []
    for a in anchors:
        lo, hi = max(0, a - 6), min(len(lines), a + 6)
        snippets.append({"line": a, "text": "\n".join(lines[lo:hi])})
    return {
        "lines": len(lines),
        "pytest_totals": totals[-3:],
        "failed_tests": failed,
        "error_tests": errors,
        "collection_errors": sorted(set(collect)),
        "exceptions": [dict(message=k, **v) for k, v in list(exceptions.items())[:25]],
        "missing_modules_own": own_missing,
        "missing_modules_third_party": third_missing,
        "cannot_import": bad_imports,
        "signals": signals,
        "repo_files_in_errors": {k: sorted(v)[:20] for k, v in sorted(files.items())[:40]},
        "exit_codes_seen": exit_codes[-5:],
        "location_votes": votes,
        "suggested_location": suggestion,
        "snippets": snippets,
        "tail": lines[-40:],
    }


def cmd_analyze(args):
    text = read(args.log)
    if not text:
        dump({"error": "log %s is empty or unreadable" % args.log})
        return 2
    res = analyze_text(text, args.repo)
    res["log"] = os.path.abspath(args.log)
    dump(res)
    return 0


# --------------------------------------------------------------------------- run

def default_repo():
    bl = os.path.join(STATE, "baseline", "meta.json")
    if os.path.isfile(bl):
        return json.load(open(bl))["repo"]
    return None


def cmd_run(args):
    repo = os.path.abspath(args.repo) if args.repo else default_repo()
    if not repo:
        dump({"error": "no --repo given and no baseline; run `locate` first"})
        return 2
    cmd = args.cmd
    if not cmd:
        loc = os.path.join(STATE, "locate.json")
        script = json.load(open(loc)).get("run_script") if os.path.isfile(loc) else None
        script = script or next((p for p in RUN_SCRIPT_CANDIDATES if os.path.isfile(p)), None)
        if not script:
            dump({"error": "no run_failed.sh found; pass --cmd with the CI test command "
                           "(see workflow_run_steps from `locate`)"})
            return 2
        cmd = "bash %s" % script
    os.makedirs(os.path.join(STATE, "runs"), exist_ok=True)
    label = args.label or time.strftime("run-%H%M%S")
    log_path = os.path.join(STATE, "runs", label + ".log")
    eprint("[buildfix] running: %s (cwd=%s, timeout=%ss) -> %s" % (cmd, repo, args.timeout, log_path))
    start = time.time()
    with open(log_path, "w") as logf:
        try:
            p = subprocess.Popen(["bash", "-c", cmd], cwd=repo, stdout=logf, stderr=subprocess.STDOUT,
                                 universal_newlines=True)
            rc = p.wait(timeout=args.timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            p.kill()
            rc, timed_out = -9, True
    res = analyze_text(read(log_path), repo)
    res.update({"label": label, "command": cmd, "exit_code": rc, "timed_out": timed_out,
                "seconds": round(time.time() - start, 1), "log": log_path})
    out_json = os.path.join(STATE, "runs", label + ".json")
    with open(out_json, "w") as f:
        json.dump(res, f, indent=1)
    res["analysis_json"] = out_json
    dump(res)
    return 0


# --------------------------------------------------------------------------- compare

def test_ids(res):
    return {t["test"] for t in res.get("failed_tests", []) + res.get("error_tests", [])} | \
           {"collect:" + c for c in res.get("collection_errors", [])}


def cmd_compare(args):
    before, after = json.load(open(args.before)), json.load(open(args.after))
    b, a = test_ids(before), test_ids(after)
    bs, as_ = set(before.get("signals", {})), set(after.get("signals", {}))
    res = {
        "exit_code_before": before.get("exit_code"), "exit_code_after": after.get("exit_code"),
        "fixed": sorted(b - a), "still_failing": sorted(a & b), "new_failures": sorted(a - b),
        "signals_cleared": sorted(bs - as_), "signals_remaining": sorted(as_ & bs),
        "signals_new": sorted(as_ - bs),
        "totals_after": after.get("pytest_totals"),
    }
    # tests that could not even run before (collection/usage errors, no pytest summary) may
    # surface as "new" failures once the blocking error is fixed: they were masked, not caused.
    masked = bool(before.get("collection_errors") or not before.get("pytest_totals") or
                  set(before.get("signals", {})) & {"pytest_usage_error", "syntax_error",
                                                    "dependency_resolution", "build_backend_failure",
                                                    "lockfile_out_of_date", "command_not_found"})
    res["before_run_was_blocked"] = masked
    res["build_green"] = after.get("exit_code") == 0 and not a
    if res["build_green"]:
        verdict = "green"
    elif (res["new_failures"] or res["signals_new"]) and masked:
        verdict = "exposed"  # progress: a blocking error is gone and previously masked failures show
    elif res["new_failures"] or res["signals_new"]:
        verdict = "regressed"
    elif res["fixed"] or res["signals_cleared"]:
        verdict = "partial"
    else:
        verdict = "unchanged"
    res["verdict"] = verdict
    dump(res)
    return 0


# --------------------------------------------------------------------------- patch

def file_lines(path):
    if path is None or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    if b"\0" in data[:8000]:
        raise ValueError("binary")
    return data.decode("utf-8", errors="surrogateescape").splitlines(True)


def unified(rel, old, new):
    """git-style unified diff for one file; old/new are line lists or None (absent)."""
    a = old or []
    b = new or []
    body = list(difflib.unified_diff(a, b, "a/" + rel if old is not None else "/dev/null",
                                     "b/" + rel if new is not None else "/dev/null", n=3))
    if not body:
        return ""
    fixed = []
    for line in body:
        if line.startswith(("---", "+++")):
            fixed.append(line.rstrip("\n") + "\n")
        elif line.endswith("\n"):
            fixed.append(line)
        else:
            fixed.append(line + "\n\\ No newline at end of file\n")
    head = "diff --git a/%s b/%s\n" % (rel, rel)
    if old is None:
        head += "new file mode 100644\n"
    elif new is None:
        head += "deleted file mode 100644\n"
    return head + "".join(fixed)


def changed_files(repo, meta):
    """Return {rel: base_path_or_None} for every file that differs from the baseline."""
    base_dir = os.path.join(STATE, "baseline", "files")
    changes = {}
    if meta["git"]:
        rc, out, _ = sh(["git", "status", "--porcelain", "-uall", "-z"], cwd=repo)
        entries = [e for e in out.split("\0") if e]
        current = {}
        for e in entries:
            current[e[3:]] = e[:2]
        for rel in set(current) | set(meta["dirty"]):
            if NOISE_FILE_RE.search(rel) or any(part in SKIP_DIRS for part in rel.split("/")):
                continue
            full = os.path.join(repo, rel)
            exists = os.path.isfile(full)
            if rel in meta["dirty"]:
                was = meta["dirty"][rel]
                now_sha = sha(full) if exists else None
                if now_sha == was["sha"]:
                    continue  # untouched since baseline
                changes[rel] = os.path.join(base_dir, rel) if was["sha"] else None
            else:
                changes[rel] = "git:HEAD"  # clean at baseline -> base is HEAD (or absent if untracked)
                if current.get(rel, "").startswith("??"):
                    changes[rel] = None
    else:
        seen = set()
        for dirpath, dirnames, filenames in os.walk(repo):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), repo)
                if NOISE_FILE_RE.search(rel):
                    continue
                seen.add(rel)
                if rel not in meta["manifest"]:
                    changes[rel] = None
                elif sha(os.path.join(repo, rel)) != meta["manifest"][rel]:
                    changes[rel] = os.path.join(base_dir, rel)
        for rel in meta["manifest"]:
            if rel not in seen and not NOISE_FILE_RE.search(rel):
                changes[rel] = os.path.join(base_dir, rel)
    return changes


def base_lines(repo, rel, base):
    if base is None:
        return None
    if base == "git:HEAD":
        rc, out, _ = sh(["git", "show", "HEAD:" + rel], cwd=repo)
        if rc != 0:
            return None
        p = subprocess.run(["git", "show", "HEAD:" + rel], cwd=repo, stdout=subprocess.PIPE)
        return p.stdout.decode("utf-8", errors="surrogateescape").splitlines(True)
    return file_lines(base)


def cmd_patch(args):
    bl = os.path.join(STATE, "baseline", "meta.json")
    if not os.path.isfile(bl):
        dump({"error": "no baseline at %s; run `locate` before editing" % bl})
        return 2
    meta = json.load(open(bl))
    repo = os.path.abspath(args.repo) if args.repo else meta["repo"]
    changes = changed_files(repo, meta)
    if not changes:
        dump({"error": "no changes since baseline; edit the repository first"})
        return 2
    diffs, skipped = [], []
    for rel in sorted(changes):
        try:
            old = base_lines(repo, rel, changes[rel])
            new = file_lines(os.path.join(repo, rel))
        except ValueError:
            skipped.append({"file": rel, "why": "binary file; not representable in a text diff"})
            continue
        d = unified(rel, old, new)
        if d:
            diffs.append((rel, d))
    for old_patch in os.listdir(repo):
        if re.match(r"patch_\d+\.diff$", old_patch):
            os.remove(os.path.join(repo, old_patch))
    written = []
    groups = [("all", "".join(d for _, d in diffs))] if args.single else diffs
    for i, (rel, text) in enumerate(groups, 1):
        path = os.path.join(repo, "patch_%d.diff" % i)
        with open(path, "w", errors="surrogateescape") as f:
            f.write(text)
        written.append({"patch": path, "files": [rel] if rel != "all" else [r for r, _ in diffs]})

    # prove: base tree + patches (in order) == current tree
    check = {"applies_in_order_on_base": False, "result_matches_worktree": False, "errors": []}
    tmp = tempfile.mkdtemp(prefix="buildfix-verify-")
    try:
        if meta["git"]:
            p1 = subprocess.Popen(["git", "archive", "HEAD"], cwd=repo, stdout=subprocess.PIPE)
            subprocess.run(["tar", "-x", "-C", tmp], stdin=p1.stdout, check=True)
            p1.wait()
            base_dir = os.path.join(STATE, "baseline", "files")
            for rel, info in meta["dirty"].items():
                src = os.path.join(base_dir, rel)
                if info["sha"] and os.path.isfile(src):
                    os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
                    shutil.copy2(src, os.path.join(tmp, rel))
        else:
            shutil.rmtree(tmp)
            shutil.copytree(os.path.join(STATE, "baseline", "files"), tmp)
        ok = True
        for w in written:
            rc, out, err = sh(["git", "apply", "--whitespace=nowarn", w["patch"]], cwd=tmp)
            if rc != 0:
                ok = False
                check["errors"].append("%s: %s" % (os.path.basename(w["patch"]), err.strip()[:400]))
        check["applies_in_order_on_base"] = ok
        mism = []
        for rel, _ in diffs:
            a, b = os.path.join(tmp, rel), os.path.join(repo, rel)
            if os.path.isfile(a) != os.path.isfile(b) or (os.path.isfile(a) and sha(a) != sha(b)):
                mism.append(rel)
        check["result_matches_worktree"] = ok and not mism
        if mism:
            check["errors"].append("content mismatch after apply: %s" % ", ".join(mism))
        if meta["git"]:
            for w in written:
                rc, _, err = sh(["git", "apply", "--check", "-R", w["patch"]], cwd=repo)
                if rc != 0 and len(written) == 1:
                    check["errors"].append("reverse-check failed (patch not reflected in worktree?): " + err.strip()[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    dump({"repo": repo, "patches": written, "skipped": skipped, "verification": check,
          "ok": check["result_matches_worktree"] and not skipped})
    return 0 if check["result_matches_worktree"] else 1


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd_name")
    p = sub.add_parser("locate")
    p.add_argument("--root", default=DEFAULT_ROOT)
    p.add_argument("--repo")
    p.add_argument("--rebaseline", action="store_true", help="discard the saved baseline and snapshot again")
    p.set_defaults(fn=cmd_locate)
    p = sub.add_parser("run")
    p.add_argument("--repo")
    p.add_argument("--cmd", help="shell command to run in the repo (default: run_failed.sh)")
    p.add_argument("--label")
    p.add_argument("--timeout", type=int, default=1800)
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("analyze")
    p.add_argument("--log", required=True)
    p.add_argument("--repo")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("compare")
    p.add_argument("before")
    p.add_argument("after")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("patch")
    p.add_argument("--repo")
    p.add_argument("--single", action="store_true", help="write one patch_1.diff instead of one per file")
    p.set_defaults(fn=cmd_patch)
    args = ap.parse_args()
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
