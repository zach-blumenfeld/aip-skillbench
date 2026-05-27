#!/usr/bin/env bash
# Capture the current working-tree changes in /root/druid as one or more
# unified-diff patch files under /root/patches/.
#
# Two modes:
#   scripts/make-patch.sh combined cve-2021-25646.patch
#       → single patch with every modified file
#   scripts/make-patch.sh per-file
#       → one patch per modified file, named after the file's basename
#
# Both modes use `git diff` so the output applies cleanly with
# `git apply` or `patch -p1`.
set -euo pipefail

MODE="${1:-combined}"
NAME="${2:-cve-2021-25646.patch}"
DRUID_ROOT="${DRUID_ROOT:-/root/druid}"
PATCH_DIR="${PATCH_DIR:-/root/patches}"

mkdir -p "$PATCH_DIR"
cd "$DRUID_ROOT"

case "$MODE" in
  combined)
    out="$PATCH_DIR/$NAME"
    git diff --no-color -- '*.java' > "$out"
    echo "Wrote $out"
    ;;
  per-file)
    git diff --name-only -- '*.java' | while read -r f; do
      [[ -z "$f" ]] && continue
      base="$(basename "$f" .java)"
      out="$PATCH_DIR/${base}.patch"
      git diff --no-color -- "$f" > "$out"
      echo "Wrote $out"
    done
    ;;
  *)
    echo "Usage: $0 {combined [name.patch] | per-file}" >&2
    exit 2
    ;;
esac
