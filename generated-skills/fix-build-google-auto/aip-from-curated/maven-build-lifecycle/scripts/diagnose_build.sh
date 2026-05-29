#!/usr/bin/env bash
# Run the standard Maven diagnostic sequence on a project and dump
# results into a single directory. Designed for build-repair triage —
# every command is read-only and the output is meant to be read by an
# agent before any edit is made.
#
# Usage:
#   diagnose_build.sh <project-dir> [output-dir] [-- mvn-extra-args ...]
#
# Defaults:
#   output-dir defaults to <project-dir>/.mvn-diagnostics/
#
# Examples:
#   diagnose_build.sh /home/travis/build/failed/google/auto/101506036
#   diagnose_build.sh . diag/ -- -Pci -DskipTests
#
# All mvn invocations run with -B (batch) and -e (stack traces). Stdout
# and stderr from each command go to a separate file so the agent can
# pick which to read.

set -u

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <project-dir> [output-dir] [-- mvn-extra-args ...]" >&2
  exit 2
fi

PROJECT_DIR="$1"; shift
OUT_DIR="${PROJECT_DIR%/}/.mvn-diagnostics"
if [ $# -gt 0 ] && [ "$1" != "--" ]; then
  OUT_DIR="$1"; shift
fi
EXTRA=()
if [ $# -gt 0 ] && [ "$1" = "--" ]; then
  shift
  EXTRA=("$@")
fi

if [ ! -d "$PROJECT_DIR" ]; then
  echo "project dir not found: $PROJECT_DIR" >&2
  exit 1
fi
if [ ! -f "$PROJECT_DIR/pom.xml" ]; then
  echo "no pom.xml at $PROJECT_DIR — is this a Maven project?" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

run() {
  local name="$1"; shift
  local out="$OUT_DIR/$name.txt"
  echo "==> $name : mvn -B -e $*" | tee -a "$OUT_DIR/index.log"
  ( cd "$PROJECT_DIR" && mvn -B -e "${EXTRA[@]}" "$@" ) >"$out" 2>&1
  local rc=$?
  echo "    exit=$rc  output=$out" | tee -a "$OUT_DIR/index.log"
  return 0
}

: > "$OUT_DIR/index.log"

# Resolved configuration — what Maven will actually do, not what the raw pom says.
run effective-pom        help:effective-pom
run effective-settings   help:effective-settings
run active-profiles      help:active-profiles

# Reactor + dependency picture.
run dependency-tree      dependency:tree -Dverbose
run dependency-analyze   dependency:analyze

# Try to compile. This is the cheapest failing-phase probe.
run compile              clean compile

# If compile passes, try tests (no install, no deploy).
if grep -q "BUILD SUCCESS" "$OUT_DIR/compile.txt"; then
  run test               test
fi

echo "" | tee -a "$OUT_DIR/index.log"
echo "diagnostics written to $OUT_DIR/" | tee -a "$OUT_DIR/index.log"
echo "open $OUT_DIR/index.log first; failing commands' output lives in the named .txt files." | tee -a "$OUT_DIR/index.log"
