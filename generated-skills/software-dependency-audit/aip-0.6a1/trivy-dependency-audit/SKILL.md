---
name: trivy-dependency-audit
description: Offline security audit of third-party dependencies with Trivy. Scans a lock file (package-lock.json, yarn.lock, requirements.txt, go.sum, Cargo.lock, ...) against a pre-downloaded Trivy vulnerability database without network access, keeps only HIGH and CRITICAL findings, picks the CVSS v3 score by source priority (NVD > GHSA > RedHat > N/A), and writes a CSV report with columns Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url. Use for dependency vulnerability scanning, CVE audits, npm audit alternatives in air-gapped environments, and security_audit.csv reports.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Audit a project's third-party dependencies for known vulnerabilities, fully offline:
  run Trivy against a dependency lock file using a pre-downloaded vulnerability database,
  then turn its JSON report into a HIGH/CRITICAL-only CSV with one row per
  package/version/CVE, a CVSS v3 score chosen by source priority, the fixed version,
  title, and reference URL. Adds the exact offline Trivy invocation, DB-location
  handling, the Trivy JSON field mapping, and the CVSS source cascade.

trigger_when:
  - A task asks for a security audit or vulnerability report of a dependency file such as package-lock.json.
  - Vulnerabilities must be found with offline tools or a local database (no internet, air-gapped, reproducible scan).
  - A CSV of HIGH/CRITICAL CVEs with package, installed version, CVSS score, fixed version, title, and URL is required.
  - Trivy is installed with a pre-downloaded DB (e.g. under ~/.cache/trivy or /root/trivy-cache).

do_not_use_when:
  - The target is a container image, Kubernetes cluster, or IaC misconfiguration scan rather than dependency vulnerabilities.
  - The task wants a live online lookup (npm audit against the registry, OSV API) and explicitly forbids a local database.
  - Only CVSS math is needed for a vector string, with no scan.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages: []
  tools:
    - trivy

steps:
  - name: scan
    kind: execution
    description: >
      Locate trivy and the offline DB (<cache-dir>/db/trivy.db), then run
      `trivy fs <target> --format json --output <tmp> --scanners vuln --skip-db-update
      --offline-scan --cache-dir <cache-dir>` (plus --include-dev-deps only if asked).
      Copies an npm lock file with a non-standard name to package-lock.json first, since
      Trivy skips files it does not recognise. Reports status instead of crashing.
    inputs:
      - name: target_file
        type: string
        description: Absolute path of the dependency lock file to audit (e.g. /root/package-lock.json).
      - name: output_csv
        type: string
        description: Absolute path where the audit CSV must be written (e.g. /root/security_audit.csv).
      - name: trivy_cache_dir
        type: string
        description: Folder holding db/trivy.db; empty string to auto-detect (~/.cache/trivy, /root/.cache/trivy, /root/trivy-cache, ./trivy-cache).
      - name: include_dev_deps
        type: boolean
        description: Pass --include-dev-deps to report npm/yarn devDependencies. false unless the task explicitly asks for dev dependencies; Trivy's default excludes them.
    script: scripts/scan.py
    timeout: 1900
    outputs:
      - name: scan_status
        type: string
        description: '"ok" when Trivy produced a JSON report, "error" otherwise.'
      - name: scan_message
        type: string
        description: One-line result, or the error with Trivy's stderr and the exact command.
      - name: trivy_report_path
        type: string
        description: Path of Trivy's raw JSON report (empty on error).
      - name: scan_summary
        type: object
        description: Command, Trivy version, cache dir, DB metadata, targets, and severity counts across all levels.
    inputs_to: scan-outcome

  - name: scan-outcome
    kind: router
    description: A completed scan goes to the report; any environment failure goes to diagnosis.
    branch_on: scan_status
    branches:
      ok: write-report
      error: diagnose-scan

  - name: write-report
    kind: execution
    description: >
      Read every Results[*].Vulnerabilities[*], keep Severity HIGH or CRITICAL, map
      PkgName/InstalledVersion/VulnerabilityID/Severity/FixedVersion/Title/PrimaryURL to the
      CSV columns, take CVSS_Score as the first numeric V3Score among nvd > ghsa > redhat,
      fill gaps with N/A, drop duplicate (Package, Version, CVE_ID) rows, and write
      Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url with csv.DictWriter
      (UTF-8, header always written, even with zero findings).
    inputs:
      - name: trivy_report_path
        type: string
      - name: output_csv
        type: string
    script: scripts/report.py
    outputs:
      - name: csv_path
        type: string
        description: Absolute path of the written CSV.
      - name: findings_count
        type: integer
        description: Number of HIGH/CRITICAL rows written.
      - name: findings_by_severity
        type: object
        description: Row counts per severity level.
      - name: findings_preview
        type: list[*]
        description: The first 10 rows, for a sanity check of the mapping.
    inputs_to: end

  - name: diagnose-scan
    kind: client_task
    description: Find why the offline scan failed, fix the environment or inputs, and give the start inputs to re-run with.
    inputs:
      - name: target_file
        type: string
      - name: trivy_cache_dir
        type: string
      - name: include_dev_deps
        type: boolean
      - name: scan_message
        type: string
      - name: scan_summary
        type: object
    template: assets/diagnose-scan.md
    references:
      - path: references/troubleshooting.md
        description: Trivy offline DB layout, the required flags, and known errors (DB not found, trivy not on PATH, empty results). Load for every diagnosis.
      - path: references/report-format.md
        description: CSV columns, Trivy-field mapping, and CVSS priority rules. Load only if the CSV must be produced from a Trivy report without scripts/report.py.
    outputs:
      - name: diagnosis
        type: string
        description: Root cause of the failure and what was checked.
      - name: retry_inputs
        type: object
        description: Corrected start inputs to re-run the procedure with, or an empty object when no retry can succeed.
    inputs_to: end

  - name: end
    kind: end
    description: >
      The scan status and message. On "ok" the CSV is at csv_path with findings_count rows;
      on "error" the run ends with a diagnosis and, when fixable, retry_inputs for a fresh run.
    inputs:
      - name: scan_status
        type: string
      - name: scan_message
        type: string

anti_patterns:
  - Dropping --skip-db-update or --offline-scan, or downloading a fresh DB, to "fix" a scan; results must come from the shipped database.
  - Filtering on the CVSS number instead of Trivy's Severity label, or reporting MEDIUM/LOW findings.
  - Taking the highest score across sources, averaging them, or falling back to CVSS v2 instead of the NVD > GHSA > RedHat V3Score cascade then N/A.
  - Leaving cells empty instead of N/A, or skipping the CSV (or its header) when there are zero findings.
  - Typing CVE rows by hand from memory or an online source instead of computing them from the Trivy report.
  - Pointing --cache-dir at the db/ folder itself; it must be the parent that contains db/trivy.db.
  - Adding --include-dev-deps when the task did not ask for dev dependencies, which changes the package set.
```
