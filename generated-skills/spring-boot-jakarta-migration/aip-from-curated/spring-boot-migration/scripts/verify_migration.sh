#!/usr/bin/env bash
# Final post-migration verification. Reports PASS / FAIL per check.
# Exits 0 if every check passes, 2 otherwise. Does NOT run mvn — caller decides
# whether to layer `mvn clean compile` and `mvn test` after a clean pom check.
#
# Usage: verify_migration.sh <pom.xml>

set -uo pipefail

POM="${1:-pom.xml}"

if [[ ! -f "$POM" ]]; then
  echo "ERROR: pom.xml not found at: $POM" >&2
  exit 1
fi

fail=0
pass() { echo "PASS: $1"; }
warn() { echo "FAIL: $1"; fail=1; }

# 1. Spring Boot parent is 3.x
sb_line=$(awk '
  /<artifactId>spring-boot-starter-parent<\/artifactId>/ { found=1; next }
  found && /<version>/ { print; exit }
' "$POM" || true)
if [[ "$sb_line" =~ \<version\>3\. ]]; then
  pass "spring-boot-starter-parent is 3.x ($(echo "$sb_line" | sed -E 's/.*<version>([^<]+)<.*/\1/'))"
else
  warn "spring-boot-starter-parent is not 3.x (found: ${sb_line:-none})"
fi

# 2. java.version is 17 or 21
jv=$(grep -oE '<java\.version>[^<]+</java\.version>' "$POM" | head -n1 | sed -E 's|</?java\.version>||g' || true)
case "$jv" in
  17|21) pass "java.version is $jv" ;;
  *)     warn "java.version is not 17 or 21 (found: ${jv:-none})" ;;
esac

# 3. No legacy javax.xml.bind / jaxb-api
if grep -qE '<groupId>javax\.xml\.bind</groupId>|<artifactId>jaxb-api</artifactId>' "$POM"; then
  warn "javax.xml.bind / jaxb-api still present"
else
  pass "no javax.xml.bind / jaxb-api"
fi

# 4. No old com.sun.xml.bind jaxb-impl / jaxb-core
if grep -qE '<artifactId>jaxb-impl</artifactId>|<artifactId>jaxb-core</artifactId>' "$POM"; then
  warn "com.sun.xml.bind jaxb-impl/jaxb-core still present"
else
  pass "no com.sun.xml.bind jaxb-impl / jaxb-core"
fi

# 5. No javax.activation
if grep -qE '<groupId>javax\.activation</groupId>' "$POM"; then
  warn "javax.activation still present"
else
  pass "no javax.activation"
fi

# 6. No monolithic jjwt and no pinned 0.9.1
if grep -qE '<artifactId>jjwt</artifactId>' "$POM"; then
  warn "monolithic jjwt still present — replace with jjwt-api / jjwt-impl / jjwt-jackson"
else
  pass "no monolithic jjwt artifact"
fi
if grep -qE '<version>0\.9\.1</version>' "$POM"; then
  warn "old jjwt version 0.9.1 still pinned somewhere"
else
  pass "no jjwt 0.9.1 version pin"
fi

if [[ "$fail" -eq 0 ]]; then
  echo
  echo "All pom.xml checks passed. Recommended next: mvn clean compile && mvn test"
  exit 0
fi

echo
echo "One or more checks failed. Resolve the issues above before running mvn."
exit 2
