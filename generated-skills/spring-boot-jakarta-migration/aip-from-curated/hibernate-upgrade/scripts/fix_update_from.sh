#!/usr/bin/env bash
# Rewrite the non-standard `update from <Entity>` HQL/JPQL form to the
# Hibernate-6-compliant `update <Entity>` form across every .java file under
# a target directory. Idempotent — re-running on already-fixed code is a no-op.
#
# Usage: scripts/fix_update_from.sh [target_dir]
#   target_dir: directory to migrate (default: current directory)
#
# Why mechanical: the optional `from` keyword was only ever a Hibernate 5
# leniency; standards-compliant JPQL does not include it. Hibernate 6's
# stricter parser rejects it. The rewrite is purely syntactic.
#
# Exit code: 0 on success, non-zero on error.

set -euo pipefail

TARGET_DIR="${1:-.}"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "error: not a directory: $TARGET_DIR" >&2
  exit 2
fi

# Portable in-place sed: GNU sed accepts `-i`, BSD/macOS sed requires an
# extension argument. Detect by probing `sed --version`.
if sed --version >/dev/null 2>&1; then
  SED_INPLACE=(sed -i)
else
  SED_INPLACE=(sed -i '')
fi

# Match `update<space(s)>from<space(s)>` (case-sensitive — JPQL keywords are
# conventionally lowercase in the source files in scope) and drop the `from `.
# No word-boundary anchor: BSD/macOS sed does not support `\b`, and the
# `update from ` substring is specific enough that incidental collisions in
# identifiers are vanishingly unlikely.
pattern='s/update[[:space:]]\{1,\}from[[:space:]]\{1,\}/update /g'

find "$TARGET_DIR" -name '*.java' -type f -exec "${SED_INPLACE[@]}" "$pattern" {} +

echo "fix complete: rewrote 'update from <Entity>' -> 'update <Entity>' in .java files"
