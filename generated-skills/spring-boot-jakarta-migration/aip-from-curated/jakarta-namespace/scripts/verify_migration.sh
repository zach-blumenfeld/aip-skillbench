#!/usr/bin/env bash
# Verify that the javax -> jakarta migration is complete.
#
# Usage: scripts/verify_migration.sh [target_dir]
#   target_dir: directory to verify (default: current directory)
#
# Checks:
#   1. No remaining `import javax.<eePkg>` for any Java EE package.
#   2. If JPA appears to be in use (any @Entity occurrence), `jakarta.persistence`
#      imports must be present somewhere — otherwise the migration is incomplete
#      and the project will fail to compile.
#
# Exit code:
#   0 — verification passed.
#   1 — old javax.* Java EE imports still present, or JPA in use without
#       jakarta.persistence imports.
#   2 — usage error.

set -euo pipefail

TARGET_DIR="${1:-.}"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "error: not a directory: $TARGET_DIR" >&2
  exit 2
fi

PACKAGES=(
  persistence
  validation
  servlet
  annotation
  transaction
  ws.rs
  mail
  jms
  xml.bind
)
ALT=$(IFS='|'; echo "${PACKAGES[*]}")

status=0

# Check 1: no remaining javax.<eePkg> imports.
echo "==> scanning for remaining javax.* Java EE imports"
if leftovers=$(grep -rn -E "import javax\.($ALT)(\.|;)" --include='*.java' "$TARGET_DIR" 2>/dev/null); then
  if [[ -n "$leftovers" ]]; then
    echo "FAIL: javax.* Java EE imports still present:" >&2
    echo "$leftovers" >&2
    status=1
  fi
fi

# Check 2: if @Entity is used, jakarta.persistence imports must be present.
echo "==> checking JPA coverage"
entity_hits=$(grep -rln -E "^[[:space:]]*@Entity\b" --include='*.java' "$TARGET_DIR" 2>/dev/null || true)
if [[ -n "$entity_hits" ]]; then
  if ! grep -rq "import jakarta\.persistence" --include='*.java' "$TARGET_DIR" 2>/dev/null; then
    echo "FAIL: @Entity classes found but no jakarta.persistence imports — migration incomplete." >&2
    echo "Affected files:" >&2
    echo "$entity_hits" >&2
    status=1
  fi
fi

if [[ $status -eq 0 ]]; then
  echo "OK: jakarta namespace migration verified."
fi

exit $status
