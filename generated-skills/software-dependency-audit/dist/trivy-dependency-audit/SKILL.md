---
name: trivy-dependency-audit
description: Offline security audit of third-party dependencies with Trivy. Scans a lock file (package-lock.json, etc.) against a pre-downloaded Trivy DB with no network access, keeps HIGH/CRITICAL findings, picks the CVSS score by source priority (NVD > GHSA > RedHat > N/A), and writes a CSV report with Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url. Use for dependency vulnerability audits, CVE reports from lock files, air-gapped or offline vulnerability scanning, and turning Trivy JSON into a CSV.
compatibility: Python >= 3.8 (stdlib only, no pip packages); trivy >= 0.40 on PATH; an offline Trivy DB at <cache-dir>/db/trivy.db (the task container has it at /root/.cache/trivy, symlinked as /root/trivy-cache).
---

# Trivy Dependency Audit (offline → CSV)

## Trigger When

- A task asks for a security audit or vulnerability report of a dependency or lock file (`package-lock.json`, `yarn.lock`, `requirements.txt`, `go.sum`, ...).
- The output is a CSV of vulnerabilities with CVE, severity, CVSS score, fixed version, title, URL.
- Scanning must work offline / air-gapped, or "use offline tools or database" is mentioned.
- You already have a Trivy JSON report and need it filtered by severity and turned into a CSV.

## Purpose

Runs one deterministic pipeline: find the pre-downloaded Trivy DB, run `trivy fs` with the offline flags so it never tries to update, filter by severity, choose one CVSS score per finding by a fixed source cascade, and write the report CSV with `N/A` for missing values. What it adds beyond general knowledge: the exact offline flag set, the score-source priority, Trivy JSON quirks, and the CSV conventions an audit grader expects.

## Procedure

Progress:
- [ ] 1. Check prerequisites
- [ ] 2. Decide the scan scope (decision `scope`)
- [ ] 3. Run the audit script
- [ ] 4. Verify the CSV against the summary
- [ ] 5. Report

### 1. Check prerequisites (client task)

Before the first script run, check `python3 --version` (>= 3.8), `trivy --version` (>= 0.40), and that a `trivy.db` exists (e.g. `ls /root/.cache/trivy/db/`). Name everything missing. Do not try to download a DB or install packages; the container ships them. If only a Trivy JSON report exists (no trivy binary), use `--from-json` in step 3.

### 2. Decide the scan scope (decision)

Read the task statement and answer:

```yaml
scope:
  severities:
    type: choice
    instructions: Which severity labels must the report contain?
    criteria:
      high_critical: The task asks for HIGH and CRITICAL only, or says nothing more specific. This is the default.
      critical_only: The task asks for CRITICAL only.
      other: The task names another set (e.g. MEDIUM and above). Pass that list to --severities.
  filter_by_score:
    type: noul
    instructions: Does the task define the cut-off by a numeric CVSS score (e.g. "CVSS >= 7.0") and not by severity level?
    criteria:
      true: The task states a numeric CVSS threshold as the inclusion rule.
      false: The task talks about severity levels (HIGH, CRITICAL) or does not say.
  include_dev_deps:
    type: noul
    instructions: Does the task explicitly ask to include development dependencies (devDependencies, dev packages)?
    criteria:
      true: The task explicitly says dev/test dependencies must be scanned too.
      false: The task just says "dependencies" or "third-party dependencies", or does not mention dev scope.
  v2_fallback:
    type: noul
    instructions: Does the task ask for a CVSS v2 score when no v3 score exists?
    criteria:
      true: The task explicitly accepts or requests CVSS v2 scores as a fallback.
      false: The task does not mention CVSS v2.
```

A false positive is the costly mistake on every question: each `true` (or a non-default severity) changes which rows appear, and the report is checked against Trivy's default output. Reconsider any close call that leans toward the non-default answer, and keep the default unless the task's wording clearly asks otherwise.

Map the answers to flags:

| Answer | Flag |
|---|---|
| `severities: high_critical` | none (default `HIGH,CRITICAL`) |
| `severities: critical_only` | `--severities CRITICAL` |
| `severities: other` | `--severities <comma list>` |
| `filter_by_score: true` | `--filter-mode score --threshold <n>` (findings with no score fall back to the label) |
| `include_dev_deps: true` | `--include-dev-deps` |
| `v2_fallback: true` | `--v2-fallback` |

### 3. Run the audit (script)

```bash
python3 scripts/audit.py /root/package-lock.json --output /root/security_audit.csv [flags from step 2]
```

Run it from the skill folder, or use the script's absolute path. Replace the target and output paths with the ones the task gives. Other useful options:
- `--cache-dir <dir>`: the dir that *contains* `db/trivy.db`. If you omit it, the script checks `/root/.cache/trivy`, `/root/trivy-cache`, `~/.cache/trivy`, and `./trivy-cache`, including nested unzip folders. If `trivy.db` sits outside a `db/` folder, the script creates `.trivy-cache/db/` symlinks next to the CSV, because Trivy needs that layout.
- `--json-out <path>`: where to keep Trivy's raw JSON (defaults to `trivy_report.json` next to the CSV).
- `--from-json <trivy.json>`: skip scanning and build the CSV from an existing report.

What the script does:
1. Runs `trivy fs <target> --format json --output <json> --scanners vuln --cache-dir <dir> --skip-db-update --offline-scan`. If Trivy rejects a flag as unknown, it retries with `--skip-update` (older Trivy).
2. Walks `Results[].Vulnerabilities[]` and keeps findings whose Trivy `Severity` label is in the set.
3. CVSS_Score uses `CVSS.nvd.V3Score`, then `ghsa.V3Score`, then `redhat.V3Score` (then `nvd.V2Score` only with `--v2-fallback`). If none exists, it writes `N/A`. Only numeric values count.
4. Maps fields: `PkgName`→Package, `InstalledVersion`→Version, `VulnerabilityID`→CVE_ID, `Severity`→Severity, `FixedVersion`→Fixed_Version (`N/A` if missing or empty), `Title`→Title (then `Description`, then `No description`), `PrimaryURL`→Url (then the first `References` entry, then `N/A`).
5. Drops exact repeats of (Package, Version, CVE_ID), then writes the CSV with `csv.DictWriter` (UTF-8, `newline=''`, header always written, even with zero rows).
6. Prints a JSON summary: findings total, rows written, rows by severity, duplicates dropped, CVSS source counts, and counts of non-CVE IDs, N/A scores, and N/A fixed versions.

Exit 1 means it printed the cause. Map the cause to the fix:
- **DB not found / "failed to initialize DB"**: find `trivy.db` (`find / -name trivy.db 2>/dev/null`) and pass its grandparent dir as `--cache-dir`.
- **`trivy` not found**: Trivy isn't on PATH. Report that it's missing; use `--from-json` only if a report already exists.
- **Any other Trivy error**: read the stderr it printed. Do not remove `--skip-db-update`/`--offline-scan`; there is no network.

### 4. Verify (client task)

Open the CSV and check it against the summary:
- The header is exactly `Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`.
- `rows_written` equals the data-row count, and `by_severity` only contains the requested labels.
- Spot-check two rows against the raw Trivy JSON (`--json-out`): the score comes from the highest-priority source that has a V3Score, and the fixed version matches `FixedVersion`.
- `rows_written: 0` with `trivy_findings_total > 0` is legitimate (nothing HIGH/CRITICAL). If `trivy_findings_total` is 0 for a large lock file, confirm the DB path and that the target is a lock file Trivy understands, and say so in the report.

### 5. Report (client task)

Tell the user the CSV path, the row counts by severity, and anything notable from the summary: non-CVE IDs, N/A scores, findings with no fixed version, and duplicates dropped.

## Gotchas

- **Filter on Trivy's `Severity` label, not on the CVSS score.** The label is the vendor severity Trivy chose (often GHSA for npm), and it can differ from the NVD score band (7.0–8.9 HIGH, 9.0–10.0 CRITICAL). A HIGH label with a 9.8 NVD score is normal; keep both as Trivy reports them.
- **Trivy skips npm devDependencies by default.** That default defines the expected scope. Don't add `--include-dev-deps` unless the task asks for it (decision `include_dev_deps`).
- **`VulnerabilityID` is sometimes a `GHSA-...` ID** (no CVE assigned). Keep it as-is in CVE_ID; don't invent a CVE.
- **`Vulnerabilities` can be `null` or missing** for clean targets, and `Results` can be missing entirely. The script handles both, and a header-only CSV is the correct output.
- **Use `N/A`, not empty strings,** for a missing score, fixed version, or URL. Write the score as Trivy's number (`9.8`), not a string with a label.
- **Never drop `--skip-db-update`.** Without it, Trivy tries to download a DB, fails offline, and you get inconsistent results across runs.
- Same package at two installed versions means two rows. Same package@version listed twice by Trivy means one row.
- The task's paths (`/root/package-lock.json`, `/root/security_audit.csv`) are container paths. Pass the real ones explicitly when running elsewhere.
