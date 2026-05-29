#!/usr/bin/env bash
# Bump Spring Boot parent version and java.version property in pom.xml using sed.
# Multi-line XML edits (dependency removal, dependency replacement) are NOT handled here —
# they must be edited manually or via OpenRewrite (see scripts/openrewrite_run.sh).
#
# Usage:
#   update_pom_versions.sh <pom.xml> <target-spring-boot-version> <target-java-version>
#
# Example:
#   update_pom_versions.sh pom.xml 3.2.0 21
#
# Supported Spring Boot 2.x → 3.x ranges (only 2.7.x is auto-bumped here; for other
# 2.x lines, follow the recommended order: upgrade to 2.7.x first, then to 3.x).

set -euo pipefail

POM="${1:?pom.xml path required}"
SB_TARGET="${2:?target Spring Boot version required, e.g. 3.2.0}"
JAVA_TARGET="${3:?target Java version required, 17 or 21}"

if [[ ! -f "$POM" ]]; then
  echo "ERROR: pom.xml not found at: $POM" >&2
  exit 1
fi

case "$JAVA_TARGET" in
  17|21) ;;
  *) echo "ERROR: Spring Boot 3 requires Java 17 or 21. Got: $JAVA_TARGET" >&2; exit 1 ;;
esac

if ! [[ "$SB_TARGET" =~ ^3\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: target Spring Boot must be 3.x.y. Got: $SB_TARGET" >&2
  exit 1
fi

# Portable in-place edit (GNU vs BSD sed)
sed_inplace() {
  if sed --version >/dev/null 2>&1; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

# Bump parent version when current is 2.7.x — only safe range for direct bump.
sed_inplace -E "s|<version>2\\.7\\.[0-9]+</version>|<version>${SB_TARGET}</version>|g" "$POM"

# Bump java.version property — replace 1.8 / 8 / 11 with the target.
sed_inplace -E "s|<java\\.version>1\\.8</java\\.version>|<java.version>${JAVA_TARGET}</java.version>|g" "$POM"
sed_inplace -E "s|<java\\.version>8</java\\.version>|<java.version>${JAVA_TARGET}</java.version>|g" "$POM"
sed_inplace -E "s|<java\\.version>11</java\\.version>|<java.version>${JAVA_TARGET}</java.version>|g" "$POM"

echo "Updated $POM: spring-boot-starter-parent → ${SB_TARGET}, java.version → ${JAVA_TARGET}"
echo "Reminder: multi-line dependency removals (JAXB, old jjwt) require manual edits or OpenRewrite."
