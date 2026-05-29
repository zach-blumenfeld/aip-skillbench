#!/usr/bin/env bash
# Detect current Spring Boot project state for migration planning.
# Outputs JSON to stdout. Non-zero exit only on missing pom.xml.
#
# Usage: detect_state.sh <path-to-pom.xml>

set -euo pipefail

POM="${1:-pom.xml}"

if [[ ! -f "$POM" ]]; then
  echo "ERROR: pom.xml not found at: $POM" >&2
  exit 1
fi

# Spring Boot parent version (capture the version line immediately after the
# spring-boot-starter-parent artifactId line). Portable across BSD/GNU awk.
sb_version=$(awk '
  /<artifactId>spring-boot-starter-parent<\/artifactId>/ { found=1; next }
  found && /<version>/ { print; exit }
' "$POM" | sed -E 's|.*<version>([^<]+)</version>.*|\1|' || true)
sb_version="${sb_version:-unknown}"

# Java version property
java_version=$(grep -oE '<java\.version>[^<]+</java\.version>' "$POM" \
  | head -n1 \
  | sed -E 's|</?java\.version>||g' || true)
java_version="${java_version:-unknown}"

# Old JAXB / javax.xml.bind presence
has_jaxb_api="false"
if grep -qE '<artifactId>jaxb-api</artifactId>|<groupId>javax\.xml\.bind</groupId>' "$POM"; then
  has_jaxb_api="true"
fi

has_jaxb_impl="false"
if grep -qE '<artifactId>jaxb-impl</artifactId>|<artifactId>jaxb-core</artifactId>' "$POM"; then
  has_jaxb_impl="true"
fi

has_javax_activation="false"
if grep -qE '<groupId>javax\.activation</groupId>' "$POM"; then
  has_javax_activation="true"
fi

# Old monolithic jjwt (pre-modular)
has_old_jjwt="false"
if grep -qE '<artifactId>jjwt</artifactId>' "$POM"; then
  has_old_jjwt="true"
fi

# Already-modular jjwt
has_modular_jjwt="false"
if grep -qE '<artifactId>jjwt-(api|impl|jackson)</artifactId>' "$POM"; then
  has_modular_jjwt="true"
fi

# OpenRewrite plugin present?
has_openrewrite="false"
if grep -qE '<artifactId>rewrite-maven-plugin</artifactId>' "$POM"; then
  has_openrewrite="true"
fi

cat <<EOF
{
  "pom_path": "$POM",
  "spring_boot_version": "$sb_version",
  "java_version": "$java_version",
  "has_jaxb_api": $has_jaxb_api,
  "has_jaxb_impl_or_core": $has_jaxb_impl,
  "has_javax_activation": $has_javax_activation,
  "has_old_monolithic_jjwt": $has_old_jjwt,
  "has_modular_jjwt": $has_modular_jjwt,
  "has_openrewrite_plugin": $has_openrewrite
}
EOF
