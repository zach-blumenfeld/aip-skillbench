# trivy-dependency-audit: source and compilation notes

## Provenance

Compiled from three curated Agent Skills, copied verbatim into this folder:

| Source | Contributes |
|--------|-------------|
| `trivy-offline-vulnerability-scanning/SKILL.md` | Offline Trivy invocation, DB layout and check, error handling, Trivy JSON shape, common issues |
| `cvss-score-extraction/SKILL.md` | CVSS ranges and versions, NVD > GHSA > RedHat > N/A cascade, type-safe extraction |
| `vulnerability-csv-reporting/SKILL.md` | CSV schema, field mapping from Trivy JSON, HIGH/CRITICAL filter, DictWriter usage |

Target task: audit `/root/package-lock.json` offline, keep HIGH/CRITICAL, write
`/root/security_audit.csv` with `Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`.
Container: `python:3.12-slim` with Trivy from the Aqua apt repo and a pre-built DB unzipped into
`/root/.cache/trivy` (symlinked as `/root/trivy-cache`). No extra Python packages, so both scripts are stdlib only.

## Graph and component-kind choices

```
scan (execution) -> scan-outcome (router on scan_status)
    ok    -> write-report (execution) -> end
    error -> diagnose-scan (client_task) -> end
```

- **scan: execution.** Locating the DB, building the fixed flag set, and running Trivy are deterministic.
  The script reports `scan_status` instead of exiting non-zero for environment problems, so a failure
  routes to diagnosis rather than killing the run.
- **scan-outcome: router.** Deterministic branch on the script's status; nothing to judge.
- **write-report: execution.** Severity filter, field mapping, CVSS cascade, N/A fills and CSV writing
  are all fixed rules (lookup and priority logic), so they live in `scripts/report.py`, not in prose.
- **diagnose-scan: client_task.** Fixing a broken environment (wrong cache path, missing binary,
  mis-named target) needs open-ended investigation on the machine. The agent gets the source's
  "Common issues" in `references/troubleshooting.md` and answers with a diagnosis plus corrected
  start inputs for a fresh run. No decision step: there is no judgment with a fixed answer space here.
- **end** returns `scan_status` and `scan_message`, the keys present on both paths. The CSV itself is
  the on-disk deliverable at `output_csv`.

## Additions beyond the sources (and why)

- **DB auto-detection** in `~/.cache/trivy`, `/root/.cache/trivy`, `/root/trivy-cache`, `./trivy-cache` and
  `$TRIVY_CACHE_DIR`, searching 3 levels deep. A stray `trivy.db` without a `db/` parent is linked into one.
  The source hardcoded `./trivy-cache`, which does not exist relative to the script's folder in the container.
- **Target staging.** `trivy fs` silently ignores files whose names it does not recognise, so an npm lock
  under another name is copied to `package-lock.json` first.
- **Header always written.** The source's generator wrote no file at all when nothing was found. The task's
  deliverable is the file, so a header-only CSV is written.
- **De-duplication** on (Package, Version, CVE_ID): the same finding can come back under several targets.
- **Title fallback** to the first 200 chars of `Description`, then `N/A` (source: `'No description'`). The
  task asks for "title/description", and the source's own design principle is N/A for missing data.
- **Url fallback** to the first `References` entry, then `N/A` (source: empty string). Same principle.
- **include_dev_deps start input**, default false. Trivy excludes npm devDependencies unless
  `--include-dev-deps` is passed. The source command omits the flag, so the default keeps the source's behaviour.
- `--quiet` added to the Trivy command so progress output stays out of stderr diagnostics.
- Corrected the source's "trivy.db: SQLite database": Trivy's DB is a BoltDB file (troubleshooting.md).

## Completeness check: where each source item lives

### trivy-offline-vulnerability-scanning
| Source item | Location |
|-------------|----------|
| Offline mode purpose (air-gapped, reproducible) | `purpose`, `trigger_when` |
| DB = trivy.db + metadata.json at `<cache>/db/trivy.db` | `scan.py` find_cache_dir/db_metadata; troubleshooting.md |
| Step 1 verify DB; download command | `scan.py` (error status); troubleshooting.md (download command, network-only) |
| Step 2 flag table (fs, json, output, scanners vuln, skip-db-update, offline-scan, cache-dir) | `scan.py` command; `scan` description; troubleshooting.md table; anti-pattern |
| Step 3 check=False, report stderr on non-zero, FileNotFoundError for trivy | `scan.py` (which() check, returncode, stderr tail into scan_message) |
| JSON output structure | `report.py` field mapping; report-format.md |
| Common issues (failed to init DB, empty results/outdated DB, command not found) | troubleshooting.md; `diagnose-scan` |
| Trivy ≥ 0.40.0, Debian install | troubleshooting.md; `requires.tools: [trivy]` |
| Python stdlib deps | `requires` (no packages) |

### cvss-score-extraction
| Source item | Location |
|-------------|----------|
| Score ranges / severity bands | report-format.md |
| v2 / v3 / v3.1; prefer v3 | `report.py` (V3Score only); report-format.md; anti-pattern |
| Sources and priority NVD > GHSA > RedHat > N/A | `report.py` CVSS_SOURCES; `write-report` description; anti-pattern |
| Nested CVSS data structure | `report.py` cvss_score |
| Basic extraction function | `report.py` cvss_score |
| Type validation (dict, numeric) from safe_get_cvss_score | `report.py` cvss_score (isinstance checks, bool excluded) |
| Best practices 1–4 | `report.py` |
| Integration into records | `report.py` main |

### vulnerability-csv-reporting
| Source item | Location |
|-------------|----------|
| Eight-column schema and order | `report.py` HEADERS; report-format.md |
| N/A not empty; consistent types | `report.py` text(); report-format.md; anti-pattern |
| DictWriter, newline='', utf-8, writeheader | `report.py` |
| Severity filter CRITICAL/HIGH | `report.py` SEVERITY_FILTER; anti-pattern |
| JSON→CSV field mapping (PkgName, InstalledVersion, VulnerabilityID, Severity, FixedVersion, Title, PrimaryURL) | `report.py`; report-format.md |
| safe_get_field (None → default) | `report.py` text() |
| Summary statistics pattern | `findings_by_severity`, `findings_count` outputs |
| Test edge cases: empty results, missing fields | functional test (below) |

## Deliberate drops

| Dropped | Rationale |
|---------|-----------|
| CVSS v2 fallback (`get_cvss_score_with_fallback`) | The task names NVD/GHSA/RedHat scores, and the sources' primary and "complete" implementations use the v3 cascade then N/A. A v2 number in the same column would mix scales. Noted in report-format.md. |
| Score-with-metadata pattern (source/version provenance) | The output schema has no column for it. report-format.md says to record it separately when a report needs provenance. |
| `is_high_severity` CVSS-threshold filter | The task filters on severity level. Filtering on Trivy's label is the rule, and the score-based filter is listed as an anti-pattern. |
| Metadata row, blank separator row, Target column, scan timestamp (CSV advanced patterns and best practices 5) | The task fixes the exact columns. Extra rows or columns would break parsing of the deliverable. |
| SLA table (24h/7d/30d/90d) | Prioritisation background. It does not affect what is reported. |
| Why-CSV, use cases, limitations, alternative formats | Background. The format is fixed by the task. |
| Why-offline challenges/benefits list | Background, summarised in `purpose`. |
| Why multiple sources / rationale for NVD first | Rationale. The rule itself is kept. |
| Console table printer (`generate_report_with_cvss`) | Superseded by the CSV report. |
| External reference links (CVSS spec, NVD calculator, GitHub advisories, Trivy docs, RFC 4180, Python csv docs) | Not actionable offline. They stay in the verbatim source copies. |

## Functional test (authoring machine)

Trivy and its DB were not available on the authoring machine, so a stub `trivy` emitting Trivy-format
JSON for a fixed advisory table, matched against the real `package-lock.json` (lockfileVersion 3,
1282 packages), stood in for it. Runs covered: the ok branch with an explicit cache dir; a mis-named lock
file with DB auto-detection via `$TRIVY_CACHE_DIR` and `include_dev_deps: true` (the dev-only json5 finding
appears only then); the error branch (bad cache dir) → diagnose-scan → retry with corrected inputs; a
`trivy.db` outside a `db/` folder; a zero-findings scan (header-only CSV); and Trivy exiting non-zero.
Verified: NVD 7.5 chosen over GHSA 5.3, GHSA-only and RedHat-only scores, CVSS-less row → N/A, MEDIUM dropped,
duplicate across targets removed, commas/quotes in titles escaped. Real CVE rows depend on the container's
DB and are computed at run time, never hardcoded.
