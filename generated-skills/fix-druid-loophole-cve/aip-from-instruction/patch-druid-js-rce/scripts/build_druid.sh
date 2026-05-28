#!/usr/bin/env bash
# Rebuild patched Apache Druid 0.20.0 exactly as the task verifier expects.
#
# Builds the indexing-service module and its dependencies (-am also-make), so
# the patched JavaScript classes in the `processing` module are recompiled into
# a fresh druid-processing-0.20.0.jar. web-console is excluded (its JS build
# OOMs); every code-quality gate is skipped so the patched files build despite
# style/forbidden-API checks.
#
# Usage: build_druid.sh [DRUID_DIR]   (default DRUID_DIR=/root/druid)
#
# DO NOT change these flags — the verifier relies on this exact invocation.
set -euo pipefail

DRUID_DIR="${1:-/root/druid}"
cd "$DRUID_DIR"

mvn clean package -DskipTests \
  -Dcheckstyle.skip=true \
  -Dpmd.skip=true \
  -Dforbiddenapis.skip=true \
  -Dspotbugs.skip=true \
  -Danimal.sniffer.skip=true \
  -Denforcer.skip=true \
  -Djacoco.skip=true \
  -Ddependency-check.skip=true \
  -pl '!web-console' -pl indexing-service -am
