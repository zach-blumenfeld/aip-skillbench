#!/usr/bin/env bash
# Run a standard Maven dependency diagnostic sweep against the project rooted
# at $1 (default: cwd). Captures the verbose dependency tree, the analyze
# report, and the effective POM into files under a working directory ($2,
# default: ./.mvn-diagnostic) and prints the paths it wrote.
#
# Exit code:
#   0  every requested goal ran (their stderr may still flag errors — read the files)
#   2  pom.xml not found in project root
#   3  mvn binary missing
#
# Usage:
#   inspect_dependencies.sh [project_dir] [out_dir]
set -u

project_dir="${1:-.}"
out_dir="${2:-${project_dir}/.mvn-diagnostic}"

if [[ ! -f "${project_dir}/pom.xml" ]]; then
  echo "ERROR: pom.xml not found in ${project_dir}" >&2
  exit 2
fi

if ! command -v mvn >/dev/null 2>&1; then
  echo "ERROR: mvn not on PATH" >&2
  exit 3
fi

mkdir -p "${out_dir}"

run() {
  local label="$1"; shift
  local out="${out_dir}/${label}.txt"
  echo "==> ${label}: mvn $*" >&2
  ( cd "${project_dir}" && mvn -B -ntp "$@" ) >"${out}" 2>&1 || true
  echo "${out}"
}

run dep-tree           dependency:tree
run dep-tree-verbose   dependency:tree -Dverbose
run dep-analyze        dependency:analyze -DignoreNonCompile=false
run effective-pom      help:effective-pom -Doutput="${out_dir}/effective-pom.xml"

# Capture a plain build attempt — many issues only surface during compile.
( cd "${project_dir}" && mvn -B -ntp -fae -e compile ) \
  >"${out_dir}/compile.txt" 2>&1 || true
echo "${out_dir}/compile.txt"

echo "==> wrote diagnostics to ${out_dir}" >&2
