"""Run Trivy offline against a dependency lock file and save its JSON report.

stdin:  {"state": {"target_file", "trivy_cache_dir", "include_dev_deps"}, ...}
stdout: {"scan_status", "scan_message", "trivy_report_path", "scan_summary"}

Never exits non-zero for an environment problem (missing trivy, DB, target):
it reports scan_status "error" with a message so the procedure can route to
diagnosis. Only a genuine bug in this script crashes it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

# File names Trivy's language analyzers recognise. A target with any other name
# is silently skipped by `trivy fs`, which looks like "no vulnerabilities".
KNOWN_LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "package.json", "requirements.txt", "Pipfile.lock", "poetry.lock", "uv.lock",
    "pom.xml", "gradle.lockfile", "go.mod", "go.sum", "Cargo.lock", "Gemfile.lock",
    "composer.lock", "packages.lock.json", "packages.config", "mix.lock",
    "pubspec.lock", "Podfile.lock", "Package.resolved", "conan.lock",
}

# Where the offline DB usually lives. The task container unzips it into
# /root/.cache/trivy (Trivy's default cache) and symlinks /root/trivy-cache.
CACHE_CANDIDATES = [
    os.environ.get("TRIVY_CACHE_DIR", ""),
    os.path.expanduser("~/.cache/trivy"),
    "/root/.cache/trivy",
    "/root/trivy-cache",
    "./trivy-cache",
]


def out(status, message, report_path="", summary=None):
    json.dump({
        "scan_status": status,
        "scan_message": message,
        "trivy_report_path": report_path,
        "scan_summary": summary or {},
    }, sys.stdout)
    sys.exit(0)


def find_cache_dir(preferred):
    """Return (cache_dir, note). cache_dir has db/trivy.db, as --cache-dir needs."""
    candidates = ([preferred] if preferred else []) + CACHE_CANDIDATES
    seen = set()
    for cand in candidates:
        if not cand:
            continue
        cand = os.path.realpath(os.path.expanduser(cand))
        if cand in seen or not os.path.isdir(cand):
            continue
        seen.add(cand)
        if os.path.isfile(os.path.join(cand, "db", "trivy.db")):
            return cand, f"found {cand}/db/trivy.db"
        # The zip may have unpacked one level deeper, or without the db/ folder.
        base_depth = cand.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(cand):
            if root.count(os.sep) - base_depth >= 3:
                dirs[:] = []
            if "trivy.db" in files:
                if os.path.basename(root) == "db":
                    return os.path.dirname(root), f"found {root}/trivy.db"
                # trivy.db without a db/ parent: build a cache dir that has one.
                shim = tempfile.mkdtemp(prefix="trivy-cache-")
                os.symlink(root, os.path.join(shim, "db"))
                return shim, f"found {root}/trivy.db outside a db/ folder; linked it as {shim}/db"
    return None, "searched: " + ", ".join(c for c in candidates if c)


def stage_target(target):
    """Give Trivy a file name it recognises; return (path_to_scan, note)."""
    name = os.path.basename(target)
    if name in KNOWN_LOCKFILES:
        return target, ""
    try:
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict) and "lockfileVersion" in data:
        tmp = tempfile.mkdtemp(prefix="trivy-target-")
        staged = os.path.join(tmp, "package-lock.json")
        shutil.copyfile(target, staged)
        return staged, f"copied {name} to {staged} so Trivy's npm analyzer picks it up"
    return target, f"warning: {name} is not a lock-file name Trivy recognises"


def db_metadata(cache_dir):
    try:
        with open(os.path.join(cache_dir, "db", "metadata.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    state = json.load(sys.stdin).get("state", {})
    target = os.path.expanduser(state.get("target_file", ""))
    include_dev = bool(state.get("include_dev_deps", False))

    trivy = shutil.which("trivy")
    if not trivy:
        out("error", "'trivy' command not found on PATH. Install Trivy "
            "(https://aquasecurity.github.io/trivy/) or add it to PATH.")
    if not target or not os.path.isfile(target):
        out("error", f"target file not found: {target!r}")

    cache_dir, cache_note = find_cache_dir(state.get("trivy_cache_dir", ""))
    if not cache_dir:
        out("error", "Trivy offline database (trivy.db) not found; " + cache_note
            + ". Pass trivy_cache_dir pointing at the folder that holds db/trivy.db.")

    scan_path, stage_note = stage_target(target)
    report_path = os.path.join(tempfile.mkdtemp(prefix="trivy-report-"), "trivy_report.json")
    command = [
        trivy, "fs", scan_path,
        "--format", "json",
        "--output", report_path,
        "--scanners", "vuln",
        "--skip-db-update",   # never touch the network for the DB
        "--offline-scan",     # no online lookups during analysis
        "--cache-dir", cache_dir,
        "--quiet",
    ]
    if include_dev:
        command.append("--include-dev-deps")

    try:
        version = subprocess.run([trivy, "--version"], capture_output=True,
                                 text=True, timeout=60).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        version = []
    try:
        res = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        out("error", "trivy scan timed out after 30 minutes: " + " ".join(command))
    if res.returncode != 0 or not os.path.isfile(report_path):
        out("error", f"trivy exited {res.returncode}: " + (res.stderr or res.stdout)[-2000:]
            + "\ncommand: " + " ".join(command))

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    results = report.get("Results") or []
    vulns = [v for r in results for v in (r.get("Vulnerabilities") or [])]
    summary = {
        "command": command,
        "trivy_version": version[0] if version else "unknown",
        "cache_dir": cache_dir,
        "cache_note": cache_note,
        "db_metadata": db_metadata(cache_dir),
        "target_note": stage_note,
        "targets": [{"Target": r.get("Target"), "Type": r.get("Type"),
                     "vulnerabilities": len(r.get("Vulnerabilities") or [])} for r in results],
        "total_vulnerabilities": len(vulns),
        "severity_counts_all": dict(Counter(v.get("Severity", "UNKNOWN") for v in vulns)),
    }
    if not results:
        # Trivy may omit Results when nothing is vulnerable, so this is not an
        # error by itself; the message flags it for a sanity check.
        out("ok", "warning: trivy returned no Results (no vulnerable packages, or the "
            "target was not recognised as a dependency file). " + stage_note,
            report_path, summary)
    out("ok", f"scanned {len(results)} target(s), {len(vulns)} vulnerabilities of all severities",
        report_path, summary)


if __name__ == "__main__":
    main()
