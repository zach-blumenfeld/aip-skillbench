#!/usr/bin/env bash
# Re-run the diagnostic sweep and compile attempt after applying a fix.
# Compares the issue count before/after by re-running diagnose_conflict.py.
#
# Usage:
#   verify_fix.sh [project_dir] [out_dir]
#
# Exit codes:
#   0  build succeeded AND no diagnosed issues remain
#   1  build still failing or new issues introduced
#   2  pom.xml not found
#   3  mvn missing
set -u

project_dir="${1:-.}"
out_dir="${2:-${project_dir}/.mvn-verify}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "${project_dir}/pom.xml" ]]; then
  echo "ERROR: pom.xml not found in ${project_dir}" >&2
  exit 2
fi
if ! command -v mvn >/dev/null 2>&1; then
  echo "ERROR: mvn not on PATH" >&2
  exit 3
fi

bash "${script_dir}/inspect_dependencies.sh" "${project_dir}" "${out_dir}" >/dev/null

# Run a fresh build attempt and capture its exit status.
( cd "${project_dir}" && mvn -B -ntp -fae clean verify ) \
  >"${out_dir}/build.txt" 2>&1
build_status=$?

issues_json="${out_dir}/issues.json"
python3 "${script_dir}/diagnose_conflict.py" "${out_dir}" >"${issues_json}" 2>/dev/null
issue_count=$(python3 -c "import json,sys; print(len(json.load(open('${issues_json}')).get('issues', [])))" 2>/dev/null || echo "?")

echo "build_status=${build_status} issue_count=${issue_count}" >&2
echo "build_log=${out_dir}/build.txt" >&2
echo "issues=${issues_json}" >&2

if [[ "${build_status}" -eq 0 && "${issue_count}" == "0" ]]; then
  exit 0
fi
exit 1
