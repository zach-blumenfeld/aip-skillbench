#!/usr/bin/env bash
# Run Maven dependency diagnostics and report where each capture landed.
#
# Usage:
#   diagnose.sh <repo-root> [groupId[:artifactId]] [--mode quick|full]
#
# Captures (always under a fresh tmpdir):
#   dependency-tree.txt    mvn dependency:tree -Dverbose=true [-Dincludes=FILTER]
#   dependency-analyze.txt mvn dependency:analyze
#   effective-pom.xml      mvn help:effective-pom   (skipped in --mode quick)
#
# Emits a single JSON object on stdout naming the captured paths so the
# caller can read whichever file the situation needs.
#
# Conventions:
#   - non-zero mvn exits are tolerated (the capture is still useful for
#     diagnosis); only a missing repo root is fatal
#   - all mvn invocations run with -B -q so logs are clean
#   - no network/installs beyond what mvn itself does

set -u

REPO_ROOT=""
FILTER=""
MODE="full"

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      MODE="${2:-full}"
      shift 2
      ;;
    --mode=*)
      MODE="${1#--mode=}"
      shift
      ;;
    *)
      if [ -z "$REPO_ROOT" ]; then
        REPO_ROOT="$1"
      elif [ -z "$FILTER" ]; then
        FILTER="$1"
      fi
      shift
      ;;
  esac
done

REPO_ROOT="${REPO_ROOT:-.}"

if [ ! -d "$REPO_ROOT" ]; then
  echo "diagnose.sh: repo root not found: $REPO_ROOT" >&2
  exit 1
fi

OUT_DIR="$(mktemp -d -t mvn-diag.XXXXXX)"
TREE="$OUT_DIR/dependency-tree.txt"
ANALYZE="$OUT_DIR/dependency-analyze.txt"
EFFECTIVE="$OUT_DIR/effective-pom.xml"

cd "$REPO_ROOT" || exit 1

TREE_ARGS=(dependency:tree -Dverbose=true "-DoutputFile=$TREE")
if [ -n "$FILTER" ]; then
  TREE_ARGS+=("-Dincludes=$FILTER")
fi

mvn -B -q "${TREE_ARGS[@]}" >/dev/null 2>&1 || true
mvn -B -q dependency:analyze >"$ANALYZE" 2>&1 || true

if [ "$MODE" != "quick" ]; then
  mvn -B -q help:effective-pom "-Doutput=$EFFECTIVE" >/dev/null 2>&1 || true
fi

python3 - "$TREE" "$ANALYZE" "$EFFECTIVE" "$MODE" <<'PY'
import json
import os
import sys

tree, analyze, effective, mode = sys.argv[1:5]
out = {
    "tree": tree if os.path.exists(tree) else None,
    "analyze": analyze if os.path.exists(analyze) else None,
    "effective_pom": effective if (mode != "quick" and os.path.exists(effective)) else None,
    "mode": mode,
}
print(json.dumps(out, indent=2))
PY
