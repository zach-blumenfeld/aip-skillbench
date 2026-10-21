#!/usr/bin/env python3
"""Offline Trivy dependency audit -> filtered CSV report.

Requires: Python >= 3.8 (stdlib only: argparse, csv, json, os, subprocess, sys, glob)
          trivy >= 0.40 on PATH (not needed with --from-json)
          a pre-downloaded Trivy DB (<cache-dir>/db/trivy.db)

Pipeline:
  1. locate the offline Trivy DB (--cache-dir, else well-known locations)
  2. trivy fs <lockfile> --format json --scanners vuln --skip-db-update --offline-scan
  3. keep only the requested severities (default HIGH,CRITICAL, by Trivy's Severity label)
  4. CVSS score cascade NVD v3 > GHSA v3 > RedHat v3 (> NVD v2 with --v2-fallback) > N/A
  5. write CSV: Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url

Exit codes: 0 ok (also when zero findings; header-only CSV is written), 1 error.
"""
import argparse
import csv
import glob
import json
import os
import subprocess
import sys

HEADERS = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score",
           "Fixed_Version", "Title", "Url"]
CVSS_SOURCES = ["nvd", "ghsa", "redhat"]  # priority order: most authoritative first
CACHE_CANDIDATES = ["/root/.cache/trivy", "/root/trivy-cache",
                    os.path.expanduser("~/.cache/trivy"), "./trivy-cache"]


def find_cache_dir(explicit, staging_root):
    """Return a cache dir that contains db/trivy.db, or exit with guidance."""
    candidates = [explicit] if explicit else CACHE_CANDIDATES
    for base in candidates:
        if not base or not os.path.isdir(base):
            continue
        if os.path.isfile(os.path.join(base, "db", "trivy.db")):
            return base
        # DB zip unpacked one or two levels deeper: use the dir that holds db/
        for hit in sorted(glob.glob(os.path.join(base, "**", "db", "trivy.db"), recursive=True)):
            return os.path.dirname(os.path.dirname(hit))
        # trivy.db unpacked without its db/ folder: stage a cache dir with symlinks Trivy accepts
        for hit in sorted(glob.glob(os.path.join(base, "**", "trivy.db"), recursive=True)):
            staged = os.path.join(staging_root, ".trivy-cache")
            os.makedirs(os.path.join(staged, "db"), exist_ok=True)
            for name in ("trivy.db", "metadata.json"):
                src, dst = os.path.join(os.path.dirname(hit), name), os.path.join(staged, "db", name)
                if os.path.exists(src) and not os.path.lexists(dst):
                    os.symlink(os.path.abspath(src), dst)
            print(f"[*] {hit} has no db/ parent; staged cache dir {staged}", file=sys.stderr)
            return staged
    print(f"[!] Error: Trivy database (db/trivy.db) not found under: {', '.join(c for c in candidates if c)}",
          file=sys.stderr)
    print("    Pass --cache-dir <dir containing db/trivy.db>. To fetch one while online: "
          "trivy image --download-db-only --cache-dir <dir>", file=sys.stderr)
    sys.exit(1)


def run_trivy(target, out_json, cache_dir, include_dev):
    base = ["trivy", "fs", target, "--format", "json", "--output", out_json,
            "--scanners", "vuln", "--cache-dir", cache_dir]
    if include_dev:
        base.append("--include-dev-deps")
    offline = ["--skip-db-update", "--offline-scan"]
    # Older Trivy (<0.47) spells --skip-db-update as --skip-update; retry once on unknown flag.
    for flags in (offline, ["--skip-update", "--offline-scan"]):
        cmd = base + flags
        print("[*] " + " ".join(cmd), file=sys.stderr)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            print("[!] Error: 'trivy' command not found on PATH. Install Trivy, or pass "
                  "--from-json <existing trivy report>.", file=sys.stderr)
            sys.exit(1)
        if r.returncode == 0:
            return
        if "unknown flag" not in r.stderr:
            break
    print("[!] Trivy scan failed:\n" + r.stderr, file=sys.stderr)
    if "failed to initialize DB" in r.stderr:
        print("    DB missing or corrupted: check --cache-dir points at the dir containing db/trivy.db.",
              file=sys.stderr)
    sys.exit(1)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def cvss_score(vuln, v2_fallback=False):
    """NVD v3 > GHSA v3 > RedHat v3 [> NVD v2] > 'N/A'. Returns (score, source)."""
    cvss = vuln.get("CVSS")
    if not isinstance(cvss, dict):
        return "N/A", None
    for src in CVSS_SOURCES:
        entry = cvss.get(src)
        if isinstance(entry, dict) and _num(entry.get("V3Score")) is not None:
            return entry["V3Score"], src + ":v3"
    if v2_fallback and isinstance(cvss.get("nvd"), dict) and _num(cvss["nvd"].get("V2Score")) is not None:
        return cvss["nvd"]["V2Score"], "nvd:v2"
    return "N/A", None


def field(vuln, key, default="N/A"):
    v = vuln.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    return v.strip() if isinstance(v, str) else v


def keep(vuln, severities, filter_mode, score, threshold):
    sev = field(vuln, "Severity", "UNKNOWN").upper()
    if filter_mode == "score" and score != "N/A":
        return score >= threshold
    return sev in severities  # label mode, or score mode with no numeric score


def build_rows(report, severities, filter_mode, threshold, v2_fallback):
    rows, seen, dupes, sources = [], set(), 0, {}
    for result in report.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:  # key may be absent or null
            score, src = cvss_score(vuln, v2_fallback)
            if not keep(vuln, severities, filter_mode, score, threshold):
                continue
            title = field(vuln, "Title", None) or field(vuln, "Description", "No description")
            url = field(vuln, "PrimaryURL", None)
            if url is None:
                refs = vuln.get("References") or []
                url = refs[0] if refs else "N/A"
            row = {
                "Package": field(vuln, "PkgName", "Unknown"),
                "Version": field(vuln, "InstalledVersion"),
                "CVE_ID": field(vuln, "VulnerabilityID"),
                "Severity": field(vuln, "Severity", "UNKNOWN").upper(),
                "CVSS_Score": score,
                "Fixed_Version": field(vuln, "FixedVersion"),
                "Title": " ".join(str(title).split()),
                "Url": url,
            }
            key = (row["Package"], row["Version"], row["CVE_ID"])
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            sources[src or "none"] = sources.get(src or "none", 0) + 1
            rows.append(row)
    return rows, dupes, sources


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", default="/root/package-lock.json",
                    help="dependency/lock file to scan (default /root/package-lock.json)")
    ap.add_argument("--output", default="/root/security_audit.csv", help="CSV path to write")
    ap.add_argument("--json-out", default=None,
                    help="where to keep Trivy's raw JSON (default: <output dir>/trivy_report.json)")
    ap.add_argument("--from-json", default=None, help="skip scanning; build the CSV from this Trivy JSON")
    ap.add_argument("--cache-dir", default=None, help="dir containing db/trivy.db (auto-detected if omitted)")
    ap.add_argument("--severities", default="HIGH,CRITICAL", help="comma list of Severity labels to keep")
    ap.add_argument("--filter-mode", choices=["label", "score"], default="label",
                    help="label: Trivy Severity label (default); score: CVSS >= --threshold, label when no score")
    ap.add_argument("--threshold", type=float, default=7.0)
    ap.add_argument("--v2-fallback", action="store_true", help="use NVD V2Score when no v3 score exists")
    ap.add_argument("--include-dev-deps", action="store_true",
                    help="also scan devDependencies (Trivy skips them by default)")
    a = ap.parse_args()

    if a.from_json:
        json_path = a.from_json
    else:
        if not os.path.isfile(a.target):
            print(f"[!] Error: target not found: {a.target}", file=sys.stderr)
            sys.exit(1)
        cache = find_cache_dir(a.cache_dir, os.path.dirname(os.path.abspath(a.output)))
        print(f"[*] Trivy DB: {os.path.join(cache, 'db', 'trivy.db')}", file=sys.stderr)
        json_path = a.json_out or os.path.join(os.path.dirname(os.path.abspath(a.output)), "trivy_report.json")
        run_trivy(a.target, json_path, cache, a.include_dev_deps)

    try:
        with open(json_path, encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[!] Error: cannot read Trivy JSON {json_path}: {e}", file=sys.stderr)
        sys.exit(1)

    severities = {s.strip().upper() for s in a.severities.split(",") if s.strip()}
    rows, dupes, sources = build_rows(report, severities, a.filter_mode, a.threshold, a.v2_fallback)

    out_dir = os.path.dirname(os.path.abspath(a.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(a.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        w.writerows(rows)

    total = sum(len(r.get("Vulnerabilities") or []) for r in report.get("Results") or [])
    counts = {}
    for r in rows:
        counts[r["Severity"]] = counts.get(r["Severity"], 0) + 1
    print(json.dumps({
        "csv": os.path.abspath(a.output),
        "trivy_json": os.path.abspath(json_path),
        "trivy_findings_total": total,
        "rows_written": len(rows),
        "by_severity": counts,
        "duplicates_dropped": dupes,
        "cvss_source_counts": sources,
        "rows_without_cve_prefix": sum(1 for r in rows if not str(r["CVE_ID"]).startswith("CVE-")),
        "rows_cvss_na": sum(1 for r in rows if r["CVSS_Score"] == "N/A"),
        "rows_fixed_na": sum(1 for r in rows if r["Fixed_Version"] == "N/A"),
    }, indent=2))


if __name__ == "__main__":
    main()
