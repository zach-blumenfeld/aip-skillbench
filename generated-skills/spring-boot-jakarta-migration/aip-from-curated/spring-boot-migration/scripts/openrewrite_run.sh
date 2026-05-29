#!/usr/bin/env bash
# Run OpenRewrite's Spring Boot 3.2 upgrade recipe against the current Maven project.
# Uses a transient -D invocation so callers do not need to permanently add the plugin
# to pom.xml — the recipe handles the full Spring Boot 2.x → 3.2 upgrade including
# javax → jakarta namespace migration.
#
# Usage:
#   openrewrite_run.sh [pom-dir]
#
# Defaults to the current directory. Requires Maven on PATH.

set -euo pipefail

DIR="${1:-.}"

if ! command -v mvn >/dev/null 2>&1; then
  echo "ERROR: mvn not found on PATH" >&2
  exit 1
fi

if [[ ! -f "$DIR/pom.xml" ]]; then
  echo "ERROR: pom.xml not found in $DIR" >&2
  exit 1
fi

cd "$DIR"

# Pinned versions from the source SKILL.md.
REWRITE_PLUGIN_VERSION="${REWRITE_PLUGIN_VERSION:-5.42.0}"
REWRITE_SPRING_VERSION="${REWRITE_SPRING_VERSION:-5.21.0}"
RECIPE="${RECIPE:-org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2}"

echo "Running OpenRewrite recipe $RECIPE"
echo "  plugin: org.openrewrite.maven:rewrite-maven-plugin:${REWRITE_PLUGIN_VERSION}"
echo "  deps:   org.openrewrite.recipe:rewrite-spring:${REWRITE_SPRING_VERSION}"

mvn -U "org.openrewrite.maven:rewrite-maven-plugin:${REWRITE_PLUGIN_VERSION}:run" \
  -Drewrite.activeRecipes="${RECIPE}" \
  -Drewrite.recipeArtifactCoordinates="org.openrewrite.recipe:rewrite-spring:${REWRITE_SPRING_VERSION}"
