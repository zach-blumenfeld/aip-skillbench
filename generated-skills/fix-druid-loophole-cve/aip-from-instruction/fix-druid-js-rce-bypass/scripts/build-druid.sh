#!/usr/bin/env bash
# Rebuild Apache Druid 0.20.0 with the flags required by the verifier.
#
# - Skip web-console: the JS bundler OOMs in the patch container.
# - Skip all code-quality plugins: checkstyle/pmd/spotbugs/forbiddenapis/
#   animal-sniffer/enforcer/jacoco/dependency-check choke on patched files.
# - Build the indexing-service module (and its dependencies) only — the
#   verifier ships indexing-service/target/*.jar to /opt/druid/lib/.
#
# Usage: scripts/build-druid.sh [/root/druid]
set -euo pipefail

DRUID_ROOT="${1:-/root/druid}"

if [[ ! -d "$DRUID_ROOT" ]]; then
  echo "Druid source tree not found at: $DRUID_ROOT" >&2
  exit 2
fi

cd "$DRUID_ROOT"

exec mvn clean package \
  -DskipTests \
  -Dcheckstyle.skip=true \
  -Dpmd.skip=true \
  -Dforbiddenapis.skip=true \
  -Dspotbugs.skip=true \
  -Danimal.sniffer.skip=true \
  -Denforcer.skip=true \
  -Djacoco.skip=true \
  -Ddependency-check.skip=true \
  -pl '!web-console' \
  -pl indexing-service -am
