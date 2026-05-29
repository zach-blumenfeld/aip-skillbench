#!/usr/bin/env bash
# Scan a directory for Hibernate 5 patterns that need migration to Hibernate 6.
#
# Usage: scripts/find_hibernate5_patterns.sh [target_dir]
#   target_dir: directory to scan (default: current directory)
#
# Output (stdout): one section per pattern category, each line in the form
#   <file>:<lineno>:<match>
# Each section is preceded by a "==> <category>" header on stdout.
#
# Exit code: 0 always. The absence of matches in any section means that
# category needs no action. Use scripts/verify_upgrade.sh after migration
# to assert nothing remains.

set -euo pipefail

TARGET_DIR="${1:-.}"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "error: not a directory: $TARGET_DIR" >&2
  exit 2
fi

scan() {
  local label="$1"; shift
  echo "==> $label"
  # Each remaining arg is a regex to OR together; pass with -e.
  local args=()
  for pat in "$@"; do
    args+=(-e "$pat")
  done
  grep -rn -E --include='*.java' "${args[@]}" "$TARGET_DIR" || true
  echo
}

# 1. Legacy Hibernate Criteria API — removed in Hibernate 6. Must be rewritten
#    to JPA Criteria (CriteriaBuilder/CriteriaQuery).
scan "legacy-criteria-api" \
  'org\.hibernate\.Criteria' \
  'session\.createCriteria\(' \
  'org\.hibernate\.criterion\.Restrictions'

# 2. Deprecated @Type(type = "...") form and @TypeDef. Must be rewritten to
#    @JdbcTypeCode(SqlTypes.X) or @Type(value = Class.class).
scan "deprecated-type-annotations" \
  '@Type\(type[[:space:]]*=' \
  '@TypeDef'

# 3. Non-standard "update from" HQL/JPQL syntax — Hibernate 6 rejects it.
#    The fix is mechanical: drop the optional "from" keyword.
scan "update-from-queries" \
  'update[[:space:]]+from[[:space:]]'

# 4. "select distinct ... join fetch" — distinct is redundant in Hibernate 6
#    for collection fetches. Safe to remove for readability/intent clarity.
scan "redundant-distinct-fetch" \
  'select[[:space:]]+distinct[[:space:]].*join[[:space:]]+fetch'

# 5. Renamed dialect references (some explicit dialect classes were removed
#    or renamed in Hibernate 6; auto-detection is preferred).
scan "dialect-references" \
  'org\.hibernate\.dialect\.[A-Za-z0-9_]+Dialect'

# 6. Legacy ID generator hints (GenericGenerator with "uuid"/"increment"/
#    "sequence" strategy strings) — prefer standard JPA generation.
scan "legacy-id-generators" \
  '@GenericGenerator' \
  'strategy[[:space:]]*=[[:space:]]*"(uuid|increment|sequence|native|identity|hilo|assigned|foreign)"'
