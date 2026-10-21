# Source and provenance: trivy-dependency-audit

## Provenance

Compiled on 2026-10-20 from three curated Agent Skills, copied verbatim here:

| Source | Contributes |
|---|---|
| `trivy-offline-vulnerability-scanning/SKILL.md` | DB check, offline `trivy fs` flag set, error handling, Trivy JSON shape |
| `cvss-score-extraction/SKILL.md` | CVSS source cascade NVD > GHSA > RedHat > N/A, v2 fallback, type validation, score-threshold filter |
| `vulnerability-csv-reporting/SKILL.md` | CSV schema and column order, DictWriter conventions, severity filter, JSON→CSV field mapping, N/A handling, summary |

Target task: an offline audit of `/root/package-lock.json` (npm CLI v8.19.4 lockfile, lockfileVersion 3, 1282 package entries) written to `/root/security_audit.csv`. The container is python:3.12-slim with Trivy from apt, and the DB is unzipped to `/root/.cache/trivy` (symlinked as `/root/trivy-cache`).

## Component kinds

| Component | Kind | Why |
|---|---|---|
| 1. Check prerequisites | client_task | Run a few version/ls commands in the environment and name what's missing. Too trivial for a script, and it must happen before any script runs. |
| 2. `scope` (severities, filter_by_score, include_dev_deps, v2_fallback) | decision | Reading the task statement to choose the scope is a judgment, but each answer comes from a fixed set and maps 1:1 to a script flag. |
| 3. `scripts/audit.py` | execution | DB lookup, command construction, flag-retry, severity filter, CVSS cascade, field mapping, N/A defaults, dedupe, and CSV writing are all deterministic rules over structured JSON. One script, because each stage feeds the next. |
| 4. Verify | client_task | Compare the CSV with the summary and the raw JSON. This needs reading and judgment about anomalies (e.g. zero findings on a large lockfile). |
| 5. Report | client_task | Free-form summary text for the user. |

## Completeness walk (source item → where it lives)

**trivy-offline-vulnerability-scanning**
- Why offline / reproducibility: Gotchas "Never drop --skip-db-update" carries the actionable part. The marketing bullets are a deliberate drop (below).
- DB layout `<cache>/db/trivy.db`, metadata.json: `find_cache_dir` in audit.py and the step 3 `--cache-dir` note. The staging step symlinks metadata.json.
- Step 1, verify the DB exists and point to `trivy image --download-db-only`: `find_cache_dir` error message.
- Flag table (`fs`, `--format json`, `--output`, `--scanners vuln`, `--skip-db-update`, `--offline-scan`, `--cache-dir`): `run_trivy`, listed in SKILL step 3.1.
- Step 3, run with `check=False`, print stderr and exit 1 on non-zero, FileNotFoundError → trivy not found: `run_trivy`, and the step 3 error mapping.
- JSON output structure (`Results[].Vulnerabilities[]` fields): `build_rows`, and the field mapping in SKILL step 3.4.
- Common issues: "failed to initialize DB" → specific hint plus step 3 mapping. "No vulnerabilities when they exist / outdated DB" → step 4 check on `trivy_findings_total == 0`. "command not found" → step 3 mapping.
- Dependencies (Trivy >= 0.40, stdlib modules): frontmatter `compatibility`, script header, step 1.
- Default paths `./trivy-cache`, `trivy_report.json`: auto-detect candidates and the `--json-out` default.

**cvss-score-extraction**
- CVSS score bands (0.1–3.9 Low … 9.0–10.0 Critical): Gotcha on label vs score band.
- Prefer v3/v3.1 over v2: cascade checks V3 first, and v2 is used only with `--v2-fallback`.
- Sources and priority NVD > GHSA > RedHat → N/A: `CVSS_SOURCES` and `cvss_score`.
- Nested data structure (`CVSS.nvd.V3Score`, …): `cvss_score`.
- Basic extraction → default behavior. Enhanced v2 fallback (`NVD v3 > GHSA v3 > RedHat v3 > NVD v2`) → `--v2-fallback` plus decision `v2_fallback`.
- Pattern 2, score with metadata (source/version): `cvss_source_counts` in the summary (`nvd:v3`, `nvd:v2`, …).
- Pattern 3, threshold filter (score >= 7.0, label fallback when N/A): `--filter-mode score --threshold`, plus decision `filter_by_score`.
- Error handling (non-dict CVSS, non-numeric scores → N/A): `cvss_score` / `_num` (bools are rejected too).
- Best practices 1–5: N/A fallback, v3>v2, hierarchy, type validation, and source documentation (summary) are all implemented.

**vulnerability-csv-reporting**
- Schema and exact column order, `Package … Url`: `HEADERS`, checked in step 4.
- Design principles: descriptive names (fixed by schema). `N/A` for missing (`field()` defaults, Gotcha). Consistent types.
- DictWriter, `newline=''`, `encoding='utf-8'`, writeheader: CSV write in `main`.
- Severity filter `['HIGH','CRITICAL']`, configurable: `--severities`, plus decision `severities`.
- Field mapping (PkgName, InstalledVersion, VulnerabilityID, Severity default UNKNOWN, FixedVersion→N/A, Title→'No description', PrimaryURL): `build_rows`, SKILL step 3.4.
- Success messages / summary statistics with counts by severity (Pattern 3): JSON summary `by_severity`, `rows_written`.
- `safe_get_field` (None → default): `field()`, which also treats empty strings as missing.
- Best practice 7, edge cases (empty results, missing fields): null/missing `Vulnerabilities`/`Results` handled, header-only CSV. Tested.

## Deliberate deviations from the sources

- **Header-only CSV when there are zero findings.** The source wrote no file in that case. An audit consumer expects the file to exist, and "no findings" is a valid result.
- **Title falls back to `Description`** before 'No description', and whitespace/newlines are collapsed. This keeps rows single-line and informative.
- **Url falls back to the first `References` entry, then `N/A`** (the source used `''`). This follows the source's own "N/A, not empty strings" principle.
- **Severity is upper-cased.** Exact repeats of (Package, Version, CVE_ID) are dropped and counted.
- **Flag retry with `--skip-update`** on "unknown flag", for Trivy < 0.47.
- **Staged `.trivy-cache/db/` symlinks** when trivy.db was unzipped without its `db/` folder.
- **`--include-dev-deps` is opt-in only** (decision `include_dev_deps`). The sources never pass it, so the default scope matches the sources' command, which skips npm devDependencies.

## Deliberate drops

- "Why offline mode" challenges and benefits lists, and "Why multiple sources": rationale only. The actionable rule (never drop `--skip-db-update`; use the cascade) is kept.
- What CVSS is, and the v2/v3/v3.1 history: general knowledge. Only the v3-over-v2 preference is actionable, and it is kept.
- CSV "when to use / limitations / alternative formats" and "Why DictWriter": rationale. Its conventions are implemented.
- Severity SLA table (24h / 7d / 30d / 90d): remediation policy, not used to produce the report.
- Pattern 1 (metadata row with scan date/tool) and Pattern 2 (Target column, multi-target): both change the required CSV schema, which the task fixes at exactly 8 columns. Adding rows or columns would break the report. Best practice 5 ("add timestamp") is dropped for the same reason.
- Trivy apt installation commands: the container ships Trivy. The skill tells the agent not to install.
- The pretty-printed console table in the CVSS "Complete Example": replaced by the JSON summary.
- External reference links (Trivy docs, CVSS spec, RFC 4180, NVD): not needed offline.
