#!/usr/bin/env bash
# Rewrite javax.* imports to jakarta.* across all .java files under a target
# directory. Idempotent: re-running on already-migrated code is a no-op.
#
# Usage: scripts/migrate_imports.sh [target_dir]
#   target_dir: directory to migrate (default: current directory)
#
# Handles both specific imports (e.g. `import javax.persistence.Entity;`) and
# wildcard imports (e.g. `import javax.persistence.*;`). Leaves JDK packages
# (javax.sql, javax.crypto, javax.net) untouched.
#
# Exit code: 0 on success, non-zero on error.

set -euo pipefail

TARGET_DIR="${1:-.}"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "error: not a directory: $TARGET_DIR" >&2
  exit 2
fi

# Java EE packages that need migration. NOT included: sql, crypto, net (JDK).
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

# Portable in-place sed: GNU sed accepts `-i`, BSD/macOS sed requires an
# extension argument. We detect by probing `sed --version`.
if sed --version >/dev/null 2>&1; then
  SED_INPLACE=(sed -i)
else
  SED_INPLACE=(sed -i '')
fi

# Apply the replacement for each package. Matches `import javax.<pkg>` and
# rewrites to `import jakarta.<pkg>`. This covers both specific and wildcard
# imports because we only anchor on the prefix.
for pkg in "${PACKAGES[@]}"; do
  # Escape dots in the package name for the regex.
  pkg_re="${pkg//./\\.}"
  pattern="s/import javax\\.${pkg_re}/import jakarta.${pkg}/g"
  # Run sed per file via find. `find -exec ... {} +` batches.
  find "$TARGET_DIR" -name '*.java' -type f -exec "${SED_INPLACE[@]}" "$pattern" {} +
done

echo "migration complete: rewrote javax.{$(IFS=,; echo "${PACKAGES[*]}")} -> jakarta.*"
