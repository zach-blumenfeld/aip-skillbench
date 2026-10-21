#!/usr/bin/env python3
"""Deterministic helpers for fixing a failed Python CI build (BugSwarm-style layout).

Launched by the AIP runtime as `python3 buildfix.py <mode>` with one JSON object on
stdin ({"state", "assets", "expects"}); prints one JSON object holding exactly the
step's declared outputs. Stdlib only, Python >= 3.6.

Modes: locate, reproduce, context, reasons, patch, apply, verify, refresh.
"""
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
                   "tox.ini", "Pipfile", "poetry.lock", "uv.lock")
SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", ".env", "node_modules",
             "__pycache__", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
             ".ruff_cache", "site-packages", ".eggs", "htmlcov", ".idea", ".vscode"}
MAX_SNAPSHOT_FILE = 5 * 1024 * 1024
MAX_SNAPSHOT_TOTAL = 400 * 1024 * 1024
CONFIG_FILES = ("pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini",
                "noxfile.py", "Makefile", ".python-version", "requirements.txt",
                "requirements-dev.txt", "requirements_dev.txt", "requirements-test.txt",
                "dev-requirements.txt", "test-requirements.txt", "constraints.txt",
                ".pre-commit-config.yaml", "mypy.ini", ".flake8", "ruff.toml",
                ".ruff.toml", "Pipfile", "conftest.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
GH_TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z\s?")


# ---------------------------------------------------------------- utilities

def fail(msg):
    sys.stderr.write("buildfix: " + msg + "\n")
    sys.exit(1)


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def read_text(path, limit=None):
    try:
        with open(path, "rb") as fh:
            data = fh.read() if limit is None else fh.read(limit)
    except (IOError, OSError):
        return None
    return data.decode("utf-8", "surrogateescape")


def write_text(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8", "surrogateescape"))


def safe_str(text):
    """JSON-safe text: replace undecodable bytes."""
    if text is None:
        return None
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def run(cmd, cwd=None, timeout=60, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, timeout=timeout, env=env,
                           universal_newlines=True, errors="replace")
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout
    except (OSError, ValueError) as exc:
        return 127, str(exc)


def head_lines(text, n):
    lines = text.splitlines()
    if len(lines) <= n:
        return text
    return "\n".join(lines[:n]) + "\n... [%d more lines truncated]" % (len(lines) - n)


def workdir_for(repo_path):
    h = hashlib.sha1(os.path.abspath(repo_path).encode("utf-8")).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), "aip-buildfix", h)


def git_env(repo_path):
    """Keep git from discovering a parent repository when repo_path is not a git root."""
    env = dict(os.environ)
    if not os.path.exists(os.path.join(repo_path, ".git")):
        env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(os.path.abspath(repo_path))
    return env


def is_project_dir(path):
    if os.path.isdir(os.path.join(path, ".git")):
        return True
    return any(os.path.exists(os.path.join(path, m)) for m in PROJECT_MARKERS)


def rel_in_repo(repo, path):
    """Map a path seen in a log (absolute, CI-runner absolute, or relative) to a repo-relative path."""
    if not path:
        return None
    path = path.strip().strip("'\"")
    if "site-packages" in path or "dist-packages" in path or path.startswith("<"):
        return None
    repo = os.path.abspath(repo)
    if os.path.isabs(path):
        ap = os.path.normpath(path)
        if ap.startswith(repo + os.sep) and os.path.isfile(ap):
            return os.path.relpath(ap, repo)
        parts = ap.strip(os.sep).split(os.sep)
        for i in range(len(parts)):
            cand = os.path.join(repo, *parts[i:])
            if os.path.isfile(cand):
                return os.path.relpath(cand, repo)
        return None
    cand = os.path.normpath(os.path.join(repo, path))
    if cand.startswith(repo + os.sep) and os.path.isfile(cand):
        return os.path.relpath(cand, repo)
    parts = os.path.normpath(path).split(os.sep)
    for i in range(1, len(parts)):
        cand = os.path.join(repo, *parts[i:])
        if os.path.isfile(cand):
            return os.path.relpath(cand, repo)
    return None


def safe_rel(repo, name):
    """Validate an agent-supplied path; return repo-relative path or None."""
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    repo = os.path.abspath(repo)
    ap = os.path.normpath(name if os.path.isabs(name) else os.path.join(repo, name))
    if not ap.startswith(repo + os.sep):
        return None
    rel = os.path.relpath(ap, repo)
    if rel.split(os.sep)[0] == ".git":
        return None
    return rel.replace(os.sep, "/")


# ---------------------------------------------------------------- locate

def find_run_script(failed_root):
    build_root = os.path.dirname(failed_root.rstrip(os.sep))
    cands = ["/usr/local/bin/run_failed.sh",
             os.path.join(build_root, "run_failed.sh"),
             os.path.join(failed_root, "run_failed.sh"),
             os.path.join(os.path.dirname(build_root), "run_failed.sh")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def find_repo(failed_root, hints):
    failed_root = os.path.abspath(failed_root)
    for h in hints:
        h = os.path.abspath(h)
        if h.startswith(failed_root + os.sep) and os.path.isdir(h) and is_project_dir(h):
            return h
    found = []
    for depth1 in sorted(os.listdir(failed_root)):
        p1 = os.path.join(failed_root, depth1)
        if not os.path.isdir(p1) or depth1 in SKIP_DIRS:
            continue
        for depth2 in sorted(os.listdir(p1)):
            p2 = os.path.join(p1, depth2)
            if os.path.isdir(p2) and depth2 not in SKIP_DIRS and is_project_dir(p2):
                found.append((0 if os.path.isdir(os.path.join(p2, ".git")) else 1, 2, p2))
        if is_project_dir(p1):
            found.append((0 if os.path.isdir(os.path.join(p1, ".git")) else 1, 1, p1))
    if found:
        # prefer depth-2 (<repo>/<id>) checkouts, git ones first, then depth-1
        found.sort(key=lambda t: (t[1] != 2, t[0]))
        return found[0][2]
    if is_project_dir(failed_root):
        return failed_root
    return None


def parse_workflow(text):
    """Line-based extraction of step names, run blocks and python versions (no PyYAML)."""
    lines = text.splitlines()
    steps, versions = [], []
    cur_name = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)-?\s*name:\s*(.+?)\s*$", line)
        if m:
            cur_name = m.group(2).strip("'\"")
        m = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
        if m:
            indent = len(m.group(1))
            val = m.group(2).strip()
            if val and val[0] in "|>":
                block = []
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if nxt.strip() == "":
                        block.append("")
                        j += 1
                        continue
                    if len(nxt) - len(nxt.lstrip()) <= indent:
                        break
                    block.append(nxt.strip())
                    j += 1
                val = "\n".join(block).strip()
                i = j - 1
            steps.append({"name": cur_name, "run": val.strip("'\"")})
        m = re.match(r"^\s*python-version:\s*(.*)$", line)
        if m:
            val = m.group(1).strip()
            if val.startswith("["):
                versions += [v.strip(" '\"") for v in val.strip("[]").split(",") if v.strip()]
            elif val:
                versions.append(val.strip("'\""))
            else:
                j = i + 1
                while j < len(lines) and re.match(r"^\s*-\s*\S", lines[j]):
                    versions.append(lines[j].strip()[1:].strip(" '\""))
                    j += 1
        i += 1
    return steps, sorted(set(v for v in versions if v))


DEPLOY = re.compile(r"twine|docker\s+push|git\s+push|gh\s+release|codecov|coveralls|"
                    r"upload|publish|deploy|curl\s+-X\s*POST|aws\s|gcloud", re.I)


def snapshot(repo, baseline):
    marker = os.path.join(baseline, ".aip-baseline-complete")
    if os.path.isfile(marker):
        return "reused"
    if os.path.isdir(baseline):
        shutil.rmtree(baseline)
    os.makedirs(baseline)
    total = 0
    skipped = 0
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for f in files:
            src = os.path.join(root, f)
            if os.path.islink(src):
                continue
            try:
                size = os.path.getsize(src)
            except OSError:
                continue
            if size > MAX_SNAPSHOT_FILE or total + size > MAX_SNAPSHOT_TOTAL:
                skipped += 1
                continue
            rel = os.path.relpath(src, repo)
            dst = os.path.join(baseline, rel)
            if not os.path.isdir(os.path.dirname(dst)):
                os.makedirs(os.path.dirname(dst))
            shutil.copy2(src, dst)
            total += size
    write_text(marker, "ok\n")
    return "created (%d bytes, %d files skipped as too large)" % (total, skipped)


def mode_locate(state):
    failed_root = os.path.abspath(state["failed_root"])
    if not os.path.isdir(failed_root):
        fail("failed_root %r does not exist" % failed_root)
    run_script = find_run_script(failed_root)
    script_text = read_text(run_script) if run_script else ""
    hints = []
    for m in re.finditer(r"\bcd\s+([^\s;&|]+)", script_text or ""):
        hints.append(m.group(1).strip("'\""))
    repo = find_repo(failed_root, hints)
    if not repo:
        fail("no project directory found under %s (looked for .git/pyproject.toml/setup.py "
             "at <failed_root>/<repo>/<id>)" % failed_root)

    # CI workflows
    workflows = []
    wf_dir = os.path.join(repo, ".github", "workflows")
    all_versions = []
    candidate_cmds = []
    if os.path.isdir(wf_dir):
        for f in sorted(os.listdir(wf_dir)):
            if not f.endswith((".yml", ".yaml")):
                continue
            steps, versions = parse_workflow(read_text(os.path.join(wf_dir, f)) or "")
            all_versions += versions
            workflows.append({"file": ".github/workflows/" + f, "python_versions": versions,
                              "run_steps": steps[:40]})
            for s in steps:
                if s["run"] and not DEPLOY.search(s["run"]) and "${{" not in s["run"]:
                    candidate_cmds.append(s["run"])
    for legacy in (".travis.yml", "tox.ini", "noxfile.py", "Makefile"):
        if os.path.isfile(os.path.join(repo, legacy)):
            workflows.append({"file": legacy, "python_versions": [], "run_steps": []})

    if run_script:
        run_command = "bash " + shlex.quote(run_script)
        run_source = "run_failed.sh (pre-generated reproduction of the failing CI job)"
    elif candidate_cmds:
        run_command = " && ".join("( %s )" % c.replace("\n", " && ") for c in candidate_cmds)
        run_source = "derived from .github/workflows run steps (no run_failed.sh found); review it"
    else:
        run_command = "python3 -m pytest -q"
        run_source = "fallback: no run_failed.sh and no workflow run steps found"

    # Project facts
    pyproject = read_text(os.path.join(repo, "pyproject.toml")) or ""
    m = re.search(r"requires-python\s*=\s*[\"']([^\"']+)", pyproject)
    requires_python = m.group(1) if m else None
    ci_text = (script_text or "") + "\n".join(s["run"] for w in workflows for s in w["run_steps"])
    if os.path.isfile(os.path.join(repo, "uv.lock")) or "[tool.uv" in pyproject or \
            re.search(r"\buv (sync|run|pip|lock)\b", ci_text):
        manager = "uv"
    elif os.path.isfile(os.path.join(repo, "poetry.lock")) or "[tool.poetry" in pyproject:
        manager = "poetry"
    elif os.path.isfile(os.path.join(repo, "Pipfile")):
        manager = "pipenv"
    elif "[tool.hatch" in pyproject or "hatchling" in pyproject:
        manager = "hatch/pip"
    else:
        manager = "pip/setuptools"
    present = [f for f in CONFIG_FILES if os.path.isfile(os.path.join(repo, f))]
    test_config = None
    if "[tool.pytest" in pyproject:
        test_config = "pyproject.toml [tool.pytest.ini_options]"
    for f, marker in (("pytest.ini", "[pytest]"), ("setup.cfg", "[tool:pytest]"), ("tox.ini", "[pytest]")):
        if test_config is None and marker in (read_text(os.path.join(repo, f)) or ""):
            test_config = "%s %s" % (f, marker)

    is_git = os.path.isdir(os.path.join(repo, ".git"))
    head = None
    if is_git and shutil.which("git"):
        rc, out = run(["git", "log", "-1", "--format=%H %s"], cwd=repo, env=git_env(repo))
        head = out.strip() if rc == 0 else None
    rc, pyv = run([sys.executable, "--version"])
    uvv = run(["uv", "--version"])[1].strip() if shutil.which("uv") else None

    work = workdir_for(repo)
    baseline = os.path.join(work, "baseline")
    snap = snapshot(repo, baseline)

    ci_summary = {
        "run_script": run_script,
        "run_script_excerpt": head_lines(safe_str(script_text or ""), 150) if run_script else None,
        "workflows": workflows,
        "ci_python_versions": sorted(set(all_versions)),
    }
    project_summary = {
        "repo_path": repo,
        "package_manager": manager,
        "requires_python": requires_python,
        "config_files_present": present,
        "pytest_config": test_config,
        "is_git_repo": is_git,
        "head_commit": head,
        "python3": pyv.strip(),
        "uv": uvv,
        "run_source": run_source,
        "baseline_snapshot": snap,
    }
    emit({"repo_path": repo, "run_command": run_command, "run_cwd": repo,
          "ci_summary": ci_summary, "project_summary": project_summary,
          "baseline_dir": baseline})


# ---------------------------------------------------------------- build + log parsing

def run_build(run_command, run_cwd, timeout, log_path):
    if not os.path.isdir(os.path.dirname(log_path)):
        os.makedirs(os.path.dirname(log_path))
    start = time.time()
    timed_out = False
    with open(log_path, "wb") as log:
        log.write(("$ %s\n(cwd: %s)\n" % (run_command, run_cwd)).encode("utf-8"))
        log.flush()
        proc = subprocess.Popen(["bash", "-c", run_command], cwd=run_cwd, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()
            rc = -9
    return rc, timed_out, round(time.time() - start, 1)


def clean_log(text):
    out = []
    for line in text.splitlines():
        line = GH_TS.sub("", ANSI.sub("", line)).rstrip("\r")
        if "\r" in line:
            line = line.split("\r")[-1]
        out.append(line)
    return out


SIGNAL_PATTERNS = [
    ("pytest-failed", re.compile(r"^(FAILED|ERROR)\s+(\S+?\.py\S*)(?:\s+-\s+(.*))?$")),
    ("collection-error", re.compile(r"^_+\s*ERROR collecting (\S+)\s*_+$")),
    ("collection-error", re.compile(r"ImportError while importing test module '([^']+)'")),
    ("lint", re.compile(r"^(\S+\.pyi?):(\d+):(\d+):\s*([A-Z]{1,4}\d{2,4})\b:?\s*(.*)$")),
    ("lint", re.compile(r"^\s*-->\s+(\S+\.pyi?):(\d+):(\d+)")),
    ("type", re.compile(r"^(\S+\.pyi?):(\d+):(?:\d+:)?\s*error:\s*(.*)$")),
    ("format", re.compile(r"[Ww]ould reformat:?\s+(\S+)")),
    ("test-location", re.compile(r"^(\S+\.py):(\d+):\s+(\w*(?:Error|Exception|Exit|Failed)\w*)$")),
    ("exception", re.compile(r"^(?:E\s+)?((?:[A-Za-z_][\w]*\.)*[A-Z]\w*(?:Error|Exception))(?::\s*(.*))?$")),
    ("dependency", re.compile(r"(ResolutionImpossible|No solution found when resolving|"
                              r"Could not find a version that satisfies|No matching distribution|"
                              r"needs to be updated, but `--locked`|--frozen|requires a different Python|"
                              r"is not compatible with|incompatible|Failed to (?:build|download|prepare|resolve)|"
                              r"Because .* depends on|metadata-generation-failed|"
                              r"subprocess-exited-with-error)", re.I)),
    ("pytest-usage", re.compile(r"(error: unrecognized arguments.*|ERROR: usage:.*|"
                                r"'[\w-]+' not found in `markers` configuration option|"
                                r"async def functions are not natively supported|"
                                r"fixture '[\w]+' not found|INTERNALERROR.*)")),
    ("shell", re.compile(r"(command not found|No such file or directory|Permission denied)")),
    ("summary", re.compile(r"^=+ (.*\b(?:failed|error|errors)\b.*) in [\d.]+s.*=+$")),
    ("exit", re.compile(r"(Process completed with exit code \d+|exited with code \d+|"
                        r"make: \*\*\* .*Error \d+)")),
]


def extract_signals(lines, repo):
    signals, seen, idx = [], set(), []
    failed_tests = []
    for n, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 2000:
            continue
        for kind, pat in SIGNAL_PATTERNS:
            m = pat.search(s)
            if not m:
                continue
            sig = {"kind": kind, "file": None, "line": None, "message": s[:400], "log_line": n + 1}
            if kind == "pytest-failed":
                node = m.group(2)
                failed_tests.append(node)
                sig["file"] = rel_in_repo(repo, node.split("::")[0])
            elif kind == "collection-error":
                sig["file"] = rel_in_repo(repo, m.group(1).split("::")[0])
            elif kind in ("lint", "type", "test-location"):
                sig["file"] = rel_in_repo(repo, m.group(1))
                sig["line"] = int(m.group(2))
            elif kind == "format":
                sig["file"] = rel_in_repo(repo, m.group(1))
            elif kind == "exception" and m.group(1) in ("Error", "Exception"):
                continue
            key = (kind, sig["file"], sig["line"], re.sub(r"\d+(\.\d+)?s\b", "", s)[:200])
            if key in seen:
                break
            seen.add(key)
            signals.append(sig)
            idx.append(n)
            break
        m = re.match(r'^\s*File "([^"]+)", line (\d+)', line) or \
            re.match(r'^(\S+\.py):(\d+): in \S+', line.strip())
        if m:
            rel = rel_in_repo(repo, m.group(1))
            if rel:
                key = ("traceback", rel, int(m.group(2)))
                if key not in seen:
                    seen.add(key)
                    signals.append({"kind": "traceback-frame", "file": rel, "line": int(m.group(2)),
                                    "message": line.strip()[:400], "log_line": n + 1})
                    idx.append(n)
    # keep the most informative first: pytest/collection/lint/type/usage/dependency, cap 80
    order = {"pytest-usage": 0, "collection-error": 0, "dependency": 0, "pytest-failed": 1,
             "lint": 1, "type": 1, "format": 1, "exception": 2, "test-location": 2,
             "traceback-frame": 3, "shell": 3, "summary": 4, "exit": 5}
    ranked = sorted(range(len(signals)), key=lambda i: (order.get(signals[i]["kind"], 6), i))
    keep = sorted(ranked[:80])
    return [signals[i] for i in keep], sorted(set(failed_tests))[:100], [idx[i] for i in keep]


def excerpt(lines, idx, budget=260):
    windows = []
    for n in idx[:25]:
        windows.append((max(0, n - 6), min(len(lines), n + 7)))
    # include pytest short summary block
    for n, line in enumerate(lines):
        if "short test summary info" in line:
            windows.append((n, min(len(lines), n + 60)))
    windows.sort()
    merged = []
    for a, b in windows:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    out, used = [], 0
    for a, b in merged:
        chunk = lines[a:b]
        if used + len(chunk) > budget:
            chunk = chunk[:max(0, budget - used)]
        if not chunk:
            break
        out.append("--- log lines %d-%d ---" % (a + 1, a + len(chunk)))
        out.extend(chunk)
        used += len(chunk)
    return "\n".join(out)


def build_and_parse(state, label):
    repo = state.get("repo_path") or state["run_cwd"]
    timeout = int(state.get("build_timeout") or 1800)
    work = workdir_for(repo)
    log_path = os.path.join(work, "logs", "%s-%d.log" % (label, int(time.time())))
    rc, timed_out, secs = run_build(state["run_command"], state["run_cwd"], timeout, log_path)
    lines = clean_log(read_text(log_path) or "")
    signals, failed_tests, idx = extract_signals(lines, repo)
    if timed_out:
        signals.insert(0, {"kind": "timeout", "file": None, "line": None,
                           "message": "build command killed after %ss timeout" % timeout,
                           "log_line": len(lines)})
    tail = "\n".join(lines[-120:])
    return {"rc": rc, "timed_out": timed_out, "seconds": secs, "log_path": log_path,
            "signals": signals, "failed_tests": failed_tests,
            "excerpt": safe_str(excerpt(lines, idx)), "tail": safe_str(tail)}


def mode_reproduce(state):
    r = build_and_parse(state, "reproduce")
    markers = any(s["kind"] in ("pytest-failed", "collection-error", "summary") for s in r["signals"])
    emit({"build_exit_code": r["rc"],
          "build_reproduced": bool(r["rc"] != 0 or r["timed_out"] or markers),
          "build_log_path": r["log_path"],
          "error_signals": r["signals"],
          "failed_tests": r["failed_tests"],
          "error_excerpt": r["excerpt"],
          "log_tail": r["tail"]})


def mode_verify(state):
    r = build_and_parse(state, "verify")
    emit({"build_passed": bool(r["rc"] == 0 and not r["timed_out"]),
          "verify_exit_code": r["rc"],
          "verify_log_path": r["log_path"],
          "verify_signals": r["signals"],
          "verify_failed_tests": r["failed_tests"],
          "verify_log_tail": r["tail"]})


# ---------------------------------------------------------------- context

def snippet(repo, rel, line, radius=12):
    text = read_text(os.path.join(repo, rel))
    if text is None:
        return None
    lines = text.splitlines()
    a, b = max(0, line - radius - 1), min(len(lines), line + radius)
    return "\n".join("%5d%s %s" % (i + 1, ">" if i + 1 == line else " ", lines[i]) for i in range(a, b))


def grep_repo(repo, pattern, limit=10):
    rx = re.compile(pattern)
    hits = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for f in files:
            if not f.endswith((".py", ".pyi", ".toml", ".cfg", ".txt", ".ini")):
                continue
            p = os.path.join(root, f)
            text = read_text(p, 2 * 1024 * 1024)
            if not text:
                continue
            for n, line in enumerate(text.splitlines()):
                if rx.search(line):
                    hits.append("%s:%d: %s" % (os.path.relpath(p, repo), n + 1, line.strip()[:200]))
                    if len(hits) >= limit:
                        return hits
    return hits


def mode_context(state):
    repo = state["repo_path"]
    loc = state["error_location"]
    signals = state.get("error_signals") or []
    want_code = loc in ("code", "both", "unclear")
    want_cfg = loc in ("build_config", "both", "unclear")
    report = {"error_location": loc}
    genv = git_env(repo)
    have_git = shutil.which("git") is not None

    if have_git and os.path.isdir(os.path.join(repo, ".git")):
        rc, log = run(["git", "log", "-5", "--format=%h %ad %s", "--date=short"], cwd=repo, env=genv)
        report["recent_commits"] = log.strip() if rc == 0 else None
        rc, stat = run(["git", "show", "--stat", "--format=%H%n%an%n%s%n%b", "HEAD"], cwd=repo, env=genv)
        report["head_commit_stat"] = head_lines(stat, 60) if rc == 0 else None
        rc, diff = run(["git", "show", "--format=", "HEAD", "--", ".", ":(exclude)*.lock",
                        ":(exclude)*.ipynb"], cwd=repo, env=genv)
        report["head_commit_diff"] = safe_str(head_lines(diff, 400)) if rc == 0 else None
        rc, st = run(["git", "status", "--short"], cwd=repo, env=genv)
        report["git_status"] = head_lines(st, 40) if rc == 0 else None

    if want_code:
        snippets, seen = [], set()
        for s in signals:
            if s.get("file") and s.get("line") and (s["file"], s["line"]) not in seen:
                seen.add((s["file"], s["line"]))
                sn = snippet(repo, s["file"], s["line"])
                if sn:
                    snippets.append({"file": s["file"], "line": s["line"], "kind": s["kind"], "code": safe_str(sn)})
            if len(snippets) >= 14:
                break
        report["code_snippets"] = snippets
        symbols = {}
        for s in signals:
            msg = s.get("message") or ""
            m = re.search(r"cannot import name '(\w+)' from '([\w.]+)'", msg)
            if m and m.group(1) not in symbols:
                symbols[m.group(1)] = {"imported_from": m.group(2),
                                       "definitions": grep_repo(repo, r"^\s*(def|class|async def)\s+%s\b|^%s\s*=" % (m.group(1), m.group(1))),
                                       "usages": grep_repo(repo, r"\b%s\b" % m.group(1), 8)}
            m = re.search(r"has no attribute '(\w+)'", msg)
            if m and m.group(1) not in symbols:
                symbols[m.group(1)] = {"definitions": grep_repo(repo, r"^\s*(def|class|async def)\s+%s\b|\b%s\s*=" % (m.group(1), m.group(1))),
                                       "usages": grep_repo(repo, r"\b%s\b" % m.group(1), 8)}
            if len(symbols) >= 6:
                break
        report["symbol_lookups"] = symbols

    modules = {}
    for s in signals:
        m = re.search(r"No module named '([\w.]+)'", s.get("message") or "")
        if m:
            top = m.group(1).split(".")[0]
            if top in modules:
                continue
            local = os.path.isdir(os.path.join(repo, top)) or os.path.isfile(os.path.join(repo, top + ".py")) \
                or os.path.isdir(os.path.join(repo, "src", top))
            modules[top] = {"is_local_package": local,
                            "declared_in": grep_repo(repo, r"[\"'\s]%s([\"'\s<>=!~\[;,]|$)" % re.escape(top).replace("_", "[-_]"), 8)}
    if modules:
        report["missing_modules"] = modules

    if want_cfg:
        cfg = {}
        for f in CONFIG_FILES:
            p = os.path.join(repo, f)
            if os.path.isfile(p):
                cfg[f] = safe_str(head_lines(read_text(p) or "", 250))
        for f in sorted(os.listdir(repo)):
            if re.match(r"requirements.*\.(txt|in)$", f) and f not in cfg:
                cfg[f] = safe_str(head_lines(read_text(os.path.join(repo, f)) or "", 150))
        report["config_files"] = cfg
        tools = {"python3": run([sys.executable, "--version"])[1].strip()}
        if shutil.which("uv"):
            tools["uv"] = run(["uv", "--version"])[1].strip()
            if os.path.isfile(os.path.join(repo, "uv.lock")):
                rc, out = run(["uv", "lock", "--check"], cwd=repo, timeout=180)
                report["uv_lock_check"] = {"exit_code": rc, "output": head_lines(safe_str(out), 40)}
        for name in ("pip", "pytest", "ruff", "mypy", "tox", "poetry"):
            path = shutil.which(name)
            if path:
                tools[name] = path
        report["tools"] = tools
    emit({"context_report": report})


# ---------------------------------------------------------------- reasons

def mode_reasons(state):
    path = os.path.join(os.path.abspath(state["failed_root"]), "failed_reasons.txt")
    lines = [state["analysis"].rstrip(), "", "-" * 72,
             "Captured build signals (reproduction run)",
             "Command: %s" % state["run_command"],
             "Exit code: %s" % state["build_exit_code"]]
    for s in (state.get("error_signals") or [])[:40]:
        loc = ""
        if s.get("file"):
            loc = s["file"] + (":%s" % s["line"] if s.get("line") else "") + " "
        lines.append("- [%s] %s%s" % (s.get("kind"), loc, s.get("message")))
    write_text(path, "\n".join(lines) + "\n")
    emit({"reasons_path": path})


# ---------------------------------------------------------------- patches

def split_lines(text):
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def make_diff(rel, old, new):
    """git-style unified diff; old/new None means file absent."""
    a = split_lines(old) if old is not None else []
    b = split_lines(new) if new is not None else []
    out = ["diff --git a/%s b/%s\n" % (rel, rel)]
    if old is None:
        out += ["new file mode 100644\n", "--- /dev/null\n", "+++ b/%s\n" % rel]
    elif new is None:
        out += ["deleted file mode 100644\n", "--- a/%s\n" % rel, "+++ /dev/null\n"]
    else:
        out += ["--- a/%s\n" % rel, "+++ b/%s\n" % rel]
    body = list(difflib.unified_diff(a, b, n=3))[2:]
    if not body:
        return None
    for line in body:
        if line.startswith("@@"):
            out.append(line if line.endswith("\n") else line + "\n")
        elif line.endswith("\n"):
            out.append(line)
        else:
            out.append(line + "\n\\ No newline at end of file\n")
    return "".join(out)


def baseline_content(repo, baseline, rel):
    p = os.path.join(baseline, rel)
    if os.path.isfile(p):
        return read_text(p)
    if os.path.isfile(os.path.join(baseline, ".aip-baseline-complete")):
        cur = os.path.join(repo, rel)
        # file skipped by the snapshot (too large) -> fall back to the working copy
        if os.path.isfile(cur) and os.path.getsize(cur) > MAX_SNAPSHOT_FILE:
            return read_text(cur)
        return None
    return read_text(os.path.join(repo, rel))


def clear_patches(repo):
    for f in os.listdir(repo):
        if re.match(r"^patch_\d+\.diff$", f):
            os.remove(os.path.join(repo, f))


def check_patches(repo, baseline, patches):
    """git apply --check each patch against a scratch copy of the original files."""
    if not shutil.which("git"):
        return "skipped: git not available"
    ok, problems = 0, []
    for p in patches:
        tmp = tempfile.mkdtemp(prefix="aip-check-")
        try:
            for rel in p["files"]:
                old = baseline_content(repo, baseline, rel)
                if old is not None:
                    write_text(os.path.join(tmp, rel), old)
            env = dict(os.environ)
            env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(tmp)
            rc, out = run(["git", "apply", "--check", "--whitespace=nowarn", p["path"]], cwd=tmp, env=env)
            if rc == 0:
                ok += 1
            else:
                problems.append("%s: %s" % (os.path.basename(p["path"]), out.strip()[:300]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    msg = "%d/%d patches pass `git apply --check` against the original files" % (ok, len(patches))
    return msg + ("; " + "; ".join(problems) if problems else "")


def write_patch_set(repo, baseline, contents):
    """contents: ordered list of (rel, new_text_or_None). Returns patch records."""
    clear_patches(repo)
    patches, i = [], 0
    for rel, new in contents:
        old = baseline_content(repo, baseline, rel)
        d = make_diff(rel, old, new)
        if d is None:
            continue
        i += 1
        path = os.path.join(repo, "patch_%d.diff" % i)
        write_text(path, d)
        patches.append({"path": path, "files": [rel]})
    return patches


def mode_patch(state):
    repo, baseline = state["repo_path"], state["baseline_dir"]
    edits = state.get("edits") or []
    order, new_content, errors = [], {}, []
    for n, e in enumerate(edits):
        if not isinstance(e, dict):
            errors.append("edit %d: not an object" % n)
            continue
        rel = safe_rel(repo, e.get("file") or e.get("path") or "")
        if not rel:
            errors.append("edit %d: invalid or out-of-repo path %r" % (n, e.get("file")))
            continue
        if re.match(r"^patch_\d+\.diff$", rel):
            errors.append("edit %d: refusing to edit patch file %s" % (n, rel))
            continue
        if rel not in new_content:
            new_content[rel] = baseline_content(repo, baseline, rel)
            order.append(rel)
        cur = new_content[rel]
        if e.get("delete"):
            new_content[rel] = None
        elif "content" in e:
            new_content[rel] = e["content"]
        elif "old" in e and "new" in e:
            old, new = e["old"], e["new"]
            if cur is None:
                if old == "":
                    new_content[rel] = new
                else:
                    errors.append("edit %d: %s does not exist; use old=\"\" or content to create it" % (n, rel))
                continue
            if old == "":
                errors.append("edit %d: empty `old` on existing file %s; use `content` for a full rewrite" % (n, rel))
                continue
            count = cur.count(old)
            if count == 0:
                # tolerate CRLF files when the agent wrote LF text
                if "\r\n" in cur and cur.count(old.replace("\n", "\r\n")) > 0:
                    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
                    count = cur.count(old)
            if count == 0:
                errors.append("edit %d: `old` text not found in %s (match the original file exactly, "
                              "including indentation)" % (n, rel))
                continue
            if count > 1 and not e.get("replace_all"):
                errors.append("edit %d: `old` text occurs %d times in %s; add surrounding lines to make it "
                              "unique or set replace_all" % (n, count, rel))
                continue
            new_content[rel] = cur.replace(old, new) if e.get("replace_all") else cur.replace(old, new, 1)
        else:
            errors.append("edit %d: needs old+new, content, or delete" % n)
    contents = [(rel, new_content[rel]) for rel in order]
    unchanged = [rel for rel, c in contents if c == baseline_content(repo, baseline, rel)]
    for rel in unchanged:
        if any(rel in e for e in errors):
            continue
        errors.append("%s: edits produce no change" % rel)
    pending = os.path.join(os.path.dirname(baseline), "pending")
    if os.path.isdir(pending):
        shutil.rmtree(pending)
    manifest = {}
    for rel, c in contents:
        if c is not None:
            write_text(os.path.join(pending, rel), c)
        manifest[rel] = c is not None
    write_text(os.path.join(pending, ".manifest.json"), json.dumps(manifest))
    patches = write_patch_set(repo, baseline, contents)
    emit({"patch_files": [p["path"] for p in patches],
          "edited_files": [p["files"][0] for p in patches],
          "edit_errors": errors,
          "patch_check": check_patches(repo, baseline, patches) if patches else "no patches written"})


def patch_targets(patch_text):
    files = []
    for m in re.finditer(r"^diff --git a/(\S+) b/(\S+)$", patch_text, re.M):
        files.append(m.group(2))
    return files


def mode_apply(state):
    repo, baseline = state["repo_path"], state["baseline_dir"]
    pending = os.path.join(os.path.dirname(baseline), "pending")
    manifest = json.loads(read_text(os.path.join(pending, ".manifest.json")) or "{}")
    applied, errors, methods = [], [], set()
    env = git_env(repo)
    for patch in state.get("patch_files") or []:
        text = read_text(patch)
        if text is None:
            errors.append("%s: missing" % patch)
            continue
        targets = patch_targets(text)
        # restore originals so the patch applies to exactly what it was written against
        for rel in targets:
            old = baseline_content(repo, baseline, rel)
            cur_path = os.path.join(repo, rel)
            cur = read_text(cur_path)
            if old is None and cur is not None:
                os.remove(cur_path)
            elif old is not None and cur != old:
                write_text(cur_path, old)
        ok = False
        if shutil.which("git"):
            rc, out = run(["git", "apply", "--whitespace=nowarn", patch], cwd=repo, env=env)
            if rc == 0:
                ok = True
                methods.add("git apply")
            else:
                errors.append("%s: git apply failed (%s); wrote content directly" % (os.path.basename(patch), out.strip()[:200]))
        if not ok:
            for rel in targets:
                if manifest.get(rel):
                    write_text(os.path.join(repo, rel), read_text(os.path.join(pending, rel)))
                elif os.path.exists(os.path.join(repo, rel)):
                    os.remove(os.path.join(repo, rel))
            methods.add("direct write")
        for rel in targets:
            want = read_text(os.path.join(pending, rel)) if manifest.get(rel) else None
            have = read_text(os.path.join(repo, rel))
            if want != have:
                errors.append("%s: content after apply differs from the intended edit" % rel)
            applied.append(rel)
    emit({"applied_files": applied, "apply_method": ", ".join(sorted(methods)) or "none",
          "apply_errors": errors})


def mode_refresh(state):
    repo, baseline = state["repo_path"], state["baseline_dir"]
    files, errors = [], []
    for f in list(state.get("edited_files") or []) + list(state.get("revised_files") or []):
        rel = safe_rel(repo, f)
        if not rel:
            errors.append("ignored invalid path %r" % f)
        elif rel not in files and not re.match(r"^patch_\d+\.diff$", rel):
            files.append(rel)
    contents = []
    for rel in files:
        p = os.path.join(repo, rel)
        contents.append((rel, read_text(p) if os.path.isfile(p) else None))
    patches = write_patch_set(repo, baseline, contents)
    check = check_patches(repo, baseline, patches) if patches else "no changes relative to the original files"
    if errors:
        check += "; " + "; ".join(errors)
    r = build_and_parse(state, "final")
    passed = bool(r["rc"] == 0 and not r["timed_out"])
    rp = state["reasons_path"]
    note = ["", "-" * 72, "Revision after first verification failed",
            state.get("revision_notes", "").rstrip(),
            "Final patch set: %s" % ", ".join(os.path.basename(p["path"]) for p in patches),
            "Final build: %s (exit %s)" % ("PASSED" if passed else "FAILED", r["rc"])]
    write_text(rp, (read_text(rp) or "") + "\n".join(note) + "\n")
    emit({"final_patch_files": [p["path"] for p in patches],
          "final_patch_check": check,
          "final_build_passed": passed,
          "final_log_tail": r["tail"]})


MODES = {"locate": mode_locate, "reproduce": mode_reproduce, "context": mode_context,
         "reasons": mode_reasons, "patch": mode_patch, "apply": mode_apply,
         "verify": mode_verify, "refresh": mode_refresh}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        fail("usage: buildfix.py {%s} < payload.json" % "|".join(MODES))
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        fail("stdin is not JSON: %s" % exc)
    state = payload.get("state", payload)
    MODES[sys.argv[1]](state)


if __name__ == "__main__":
    main()
