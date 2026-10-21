The offline Trivy scan for `{target_file}` did not complete.

Scan message:

{scan_message}

Scan details (may be empty): {scan_summary}

Start inputs used: trivy_cache_dir=`{trivy_cache_dir}`, include_dev_deps=`{include_dev_deps}`.

Diagnose the cause and fix what you can on this machine, without network access to the vulnerability database:

1. Load `references/troubleshooting.md` and match the message to a known issue.
2. Check the facts yourself: `which trivy`, `trivy --version`, `ls -la` the target, and `find / -name trivy.db -not -path '/proc/*' 2>/dev/null` to locate the offline database. The cache dir passed to `--cache-dir` is the folder that *contains* `db/trivy.db`.
3. Do not download or update the database, and do not drop `--skip-db-update` / `--offline-scan`: the audit must be reproducible against the shipped database.
4. Decide the corrected start inputs (usually `trivy_cache_dir`, or a corrected `target_file`) and re-run this procedure from the start with them. If the cause cannot be fixed here, say exactly what is missing.

Answer with:
- `diagnosis`: the root cause and what you checked.
- `retry_inputs`: the corrected start-input object to re-run with (`target_file`, `output_csv`, `trivy_cache_dir`, `include_dev_deps`), or an empty object if no retry can succeed.
