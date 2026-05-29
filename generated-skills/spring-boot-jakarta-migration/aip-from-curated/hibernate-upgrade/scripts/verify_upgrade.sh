#!/usr/bin/env bash
# Verify that the Hibernate 5 -> 6 upgrade is complete in .java sources.
#
# Usage: scripts/verify_upgrade.sh [target_dir]
#   target_dir: directory to verify (default: current directory)
#
# Checks (each is independently a failure):
#   1. No `org.hibernate.Criteria` references (legacy Criteria API was removed).
#   2. No `session.createCriteria(` calls.
#   3. No `org.hibernate.criterion.Restrictions` imports.
#   4. No `@Type(type = "...")` annotations (replaced by @JdbcTypeCode or
#      @Type(value = ...)).
#   5. No `@TypeDef` annotations.
#   6. No `update from <Entity>` HQL/JPQL syntax.
#
# Exit code:
#   0 — verification passed.
#   1 — at least one Hibernate 5 pattern still present.
#   2 — usage error.

set -euo pipefail

TARGET_DIR="${1:-.}"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "error: not a directory: $TARGET_DIR" >&2
  exit 2
fi

status=0

check() {
  local label="$1"; shift
  local pattern="$1"
  echo "==> $label"
  if hits=$(grep -rn -E --include='*.java' "$pattern" "$TARGET_DIR" 2>/dev/null); then
    if [[ -n "$hits" ]]; then
      echo "FAIL: $label still present:" >&2
      echo "$hits" >&2
      status=1
      return
    fi
  fi
}

check "legacy Criteria API (org.hibernate.Criteria)" 'org\.hibernate\.Criteria[^Q]'
check "session.createCriteria(" 'session\.createCriteria\('
check "Hibernate 5 Restrictions" 'org\.hibernate\.criterion\.Restrictions'
check "deprecated @Type(type = ...)" '@Type\(type[[:space:]]*='
check "@TypeDef" '@TypeDef'
check "update from <Entity>" 'update[[:space:]]+from[[:space:]]'

if [[ $status -eq 0 ]]; then
  echo "OK: Hibernate 5 -> 6 upgrade verified (no legacy patterns remain)."
fi

exit $status
