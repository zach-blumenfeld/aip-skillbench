# Audit CSV format and CVSS rules (what scripts/report.py implements)

Columns, in order: `Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`.

| Column | Trivy JSON field | Missing value |
|--------|------------------|---------------|
| Package | `PkgName` | N/A |
| Version | `InstalledVersion` | N/A |
| CVE_ID | `VulnerabilityID` (may be a GHSA-… id when no CVE exists; keep it) | N/A |
| Severity | `Severity` (upper-case) | row dropped unless HIGH/CRITICAL |
| CVSS_Score | `CVSS.<source>.V3Score`, priority nvd > ghsa > redhat | N/A |
| Fixed_Version | `FixedVersion` (may list several, e.g. `3.0.5, 2.0.1`; keep verbatim) | N/A |
| Title | `Title`, else first 200 chars of `Description` | N/A |
| Url | `PrimaryURL`, else first of `References` | N/A |

Rules:
- Walk every `Results[*].Vulnerabilities[*]`; a result with no `Vulnerabilities` key has none.
- Keep only Severity in {CRITICAL, HIGH}. Filter on Trivy's `Severity` label, not on the CVSS number: Trivy picks the label from the ecosystem's vendor source, so a HIGH label may carry an NVD score of 9.8 and vice versa.
- CVSS: CVSS v3/v3.1 only; take the first source that has a numeric `V3Score`; never average or take the max. Ranges: 0.1–3.9 Low, 4.0–6.9 Medium, 7.0–8.9 High, 9.0–10.0 Critical. CVSS v2 (`V2Score`) is legacy and is not used for the column; when a report needs provenance, record the source (nvd/ghsa/redhat) and version separately.
- Use `N/A`, never empty cells. One row per (Package, Version, CVE_ID). Always write the header row, even with zero findings.
- Write with `csv.DictWriter`, `newline=''`, `encoding='utf-8'` so commas and quotes in titles are escaped correctly.
