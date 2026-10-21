# Trivy offline scan: troubleshooting

## Offline database layout
- Trivy's vulnerability DB is `trivy.db` (BoltDB file holding CVE/advisory data) plus `metadata.json` (DB version, update timestamp).
- It must sit at `<cache-dir>/db/trivy.db`; `--cache-dir <cache-dir>` points at the parent of `db/`.
- Default cache dir is `~/.cache/trivy`. In the audit container the DB is unzipped into `/root/.cache/trivy`, with `/root/trivy-cache` symlinked to it.
- `scripts/scan.py` searches `trivy_cache_dir`, `$TRIVY_CACHE_DIR`, `~/.cache/trivy`, `/root/.cache/trivy`, `/root/trivy-cache`, `./trivy-cache` (up to 3 levels deep) and links a stray `trivy.db` into a `db/` folder itself.
- With network access (never during the audit), a DB is fetched with `trivy image --download-db-only --cache-dir <dir>`.

## Required flags (do not drop)
| Flag | Purpose |
|------|---------|
| `fs <target>` | Scan a filesystem path or a single lock file |
| `--format json` | Machine-parseable output |
| `--output <file>` | Write the report to a file |
| `--scanners vuln` | Vulnerabilities only (no misconfig/secret scanning) |
| `--skip-db-update` | Critical: never update the DB |
| `--offline-scan` | No online lookups during analysis |
| `--cache-dir <path>` | Folder holding `db/trivy.db` |

`--include-dev-deps` adds npm/yarn devDependencies (excluded by default); use only when the task asks for dev dependencies.

## Known issues
- **"failed to initialize DB" / "database not found"**: DB missing, corrupted, or `--cache-dir` points at the wrong level (e.g. at `db/` itself). Point it at the parent of `db/`.
- **"command not found: trivy"**: Trivy not installed or not on PATH. Version 0.40.0 or later recommended. Debian/Ubuntu install (needs network): add `https://aquasecurity.github.io/trivy-repo/deb` apt repo with its key, then `apt-get install trivy`.
- **Scan finds no vulnerabilities when they exist**: (a) the DB is outdated (a newer DB must be fetched before going offline), or (b) the target file name is not one Trivy recognises (e.g. `deps.json` instead of `package-lock.json`); copy it to a correctly named file. `scan.py` does this for npm lock files automatically.
- **Non-zero exit with "--offline-scan" or "--skip-db-update" unknown**: Trivy is older than these flags; upgrade Trivy rather than removing the flags.
