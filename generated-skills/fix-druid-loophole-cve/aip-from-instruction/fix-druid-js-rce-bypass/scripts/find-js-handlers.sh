#!/usr/bin/env bash
# Locate every class in the Druid source tree that constructs a
# JavaScriptConfig or carries it as an @JacksonInject parameter — these are
# the patch sites for CVE-2021-25646.
#
# Usage: scripts/find-js-handlers.sh [/root/druid]
set -euo pipefail

DRUID_ROOT="${1:-/root/druid}"

if [[ ! -d "$DRUID_ROOT" ]]; then
  echo "Druid source tree not found at: $DRUID_ROOT" >&2
  exit 2
fi

cd "$DRUID_ROOT"

echo "=== Files referencing JavaScriptConfig ==="
git grep -l "JavaScriptConfig" -- '*.java' || true

echo
echo "=== @JacksonInject JavaScriptConfig parameters (likely patch sites) ==="
git grep -nE "@JacksonInject[[:space:]]+JavaScriptConfig" -- '*.java' || true

echo
echo "=== @JsonCreator constructors in JS-named classes ==="
git grep -l -E "class JavaScript[A-Za-z]+" -- '*.java' \
  | while read -r f; do
      echo "--- $f"
      grep -nE "@JsonCreator|@JsonProperty|@JacksonInject|@JsonAnySetter" "$f" || true
    done

echo
echo "=== Sampler endpoint (target of the published exploit) ==="
git grep -l "indexer/v1/sampler" -- '*.java' || true
