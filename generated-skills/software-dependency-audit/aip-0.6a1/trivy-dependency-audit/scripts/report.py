"""Turn a Trivy JSON report into the HIGH/CRITICAL security-audit CSV.

stdin:  {"state": {"trivy_report_path", "output_csv"}, ...}
stdout: {"csv_path", "findings_count", "findings_by_severity", "findings_preview"}
"""
import csv
import json
import os
import sys
from collections import Counter

HEADERS = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score",
           "Fixed_Version", "Title", "Url"]
SEVERITY_FILTER = ("CRITICAL", "HIGH")   # the task reports only these levels
CVSS_SOURCES = ("nvd", "ghsa", "redhat")  # priority: NVD > GHSA > RedHat > N/A
NA = "N/A"


def text(value):
    """Missing, None, or blank -> N/A (never an empty cell)."""
    if value is None:
        return NA
    value = str(value).strip()
    return value if value else NA


def cvss_score(vuln):
    """First numeric CVSS v3 score in source priority order, else N/A."""
    cvss = vuln.get("CVSS")
    if not isinstance(cvss, dict):
        return NA
    for source in CVSS_SOURCES:
        entry = cvss.get(source)
        if isinstance(entry, dict):
            score = entry.get("V3Score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                return score
    return NA


def title(vuln):
    t = (vuln.get("Title") or "").strip()
    if t:
        return t
    desc = " ".join((vuln.get("Description") or "").split())
    return desc[:200] if desc else NA


def url(vuln):
    if vuln.get("PrimaryURL"):
        return vuln["PrimaryURL"]
    refs = vuln.get("References") or []
    return refs[0] if refs else NA


def main():
    state = json.load(sys.stdin).get("state", {})
    with open(state["trivy_report_path"], encoding="utf-8") as f:
        report = json.load(f)

    rows, seen = [], set()
    for result in report.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            severity = (vuln.get("Severity") or "UNKNOWN").upper()
            if severity not in SEVERITY_FILTER:
                continue
            row = {
                "Package": text(vuln.get("PkgName")),
                "Version": text(vuln.get("InstalledVersion")),
                "CVE_ID": text(vuln.get("VulnerabilityID")),
                "Severity": severity,
                "CVSS_Score": cvss_score(vuln),
                "Fixed_Version": text(vuln.get("FixedVersion")),
                "Title": title(vuln),
                "Url": url(vuln),
            }
            # The same package@version can appear under several targets/paths.
            key = (row["Package"], row["Version"], row["CVE_ID"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    out_path = state["output_csv"]
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    # Always write the header, even with zero findings: the file is the deliverable.
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    json.dump({
        "csv_path": os.path.abspath(out_path),
        "findings_count": len(rows),
        "findings_by_severity": {s: n for s, n in Counter(r["Severity"] for r in rows).items()},
        "findings_preview": rows[:10],
    }, sys.stdout)


if __name__ == "__main__":
    main()
