#!/usr/bin/env bash
# Locate the legacy javax.xml.bind / javax.activation / monolithic jjwt dependencies
# that MUST be removed before Spring Boot 3 will build cleanly.
# Exit 0 = clean. Exit 2 = legacy deps still present (with line-numbered output to stdout).
#
# Usage: check_jaxb_removal.sh <pom.xml>

set -uo pipefail

POM="${1:-pom.xml}"

if [[ ! -f "$POM" ]]; then
  echo "ERROR: pom.xml not found at: $POM" >&2
  exit 1
fi

found=0

scan() {
  local label="$1"; local pattern="$2"
  local hits
  hits=$(grep -nE "$pattern" "$POM" || true)
  if [[ -n "$hits" ]]; then
    echo "[$label] still present in $POM:"
    echo "$hits"
    echo
    found=1
  fi
}

scan "javax.xml.bind / jaxb-api" '<groupId>javax\.xml\.bind</groupId>|<artifactId>jaxb-api</artifactId>'
scan "com.sun.xml.bind jaxb-impl / jaxb-core" '<artifactId>jaxb-impl</artifactId>|<artifactId>jaxb-core</artifactId>'
scan "javax.activation" '<groupId>javax\.activation</groupId>'
scan "monolithic jjwt (pre-modular)" '<artifactId>jjwt</artifactId>'

if [[ "$found" -eq 0 ]]; then
  echo "Clean: no legacy javax.* / monolithic jjwt dependencies found."
  exit 0
fi

echo "Action required: remove the dependency blocks above. See references/pom-snippets.md"
echo "for the Jakarta replacements when XML binding is actually needed."
exit 2
