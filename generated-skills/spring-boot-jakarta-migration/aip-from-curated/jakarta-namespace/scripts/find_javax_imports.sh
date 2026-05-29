#!/usr/bin/env bash
# Scan a directory for javax.* imports that need migration to jakarta.*.
# Excludes JDK packages (javax.sql, javax.crypto, javax.net) which stay on javax.
#
# Usage: scripts/find_javax_imports.sh [target_dir]
#   target_dir: directory to scan (default: current directory)
#
# Output (stdout): one line per match: <file>:<lineno>:<import statement>
# Exit code: 0 always. The absence of output means no migration is needed.

set -euo pipefail

TARGET_DIR="${1:-.}"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "error: not a directory: $TARGET_DIR" >&2
  exit 2
fi

# Java EE packages that need migration. Wildcards and sub-packages are matched
# via the `javax\.<pkg>` prefix.
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

# Build an alternation regex like (persistence|validation|servlet|...)
ALT=$(IFS='|'; echo "${PACKAGES[*]}")

# Match `import javax.<one-of-the-packages>` only. Anything else (javax.sql,
# javax.crypto, javax.net) is left alone.
grep -rn -E "import javax\.($ALT)(\.|;)" --include='*.java' "$TARGET_DIR" || true
