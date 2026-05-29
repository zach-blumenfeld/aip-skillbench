#!/usr/bin/env bash
# Verify Jakarta namespace migration over a Java source tree:
#   1. NO remaining migration-candidate `javax.*` imports.
#   2. JPA entity classes have at least one `jakarta.persistence` import.
#   3. Any file containing `@Entity` is paired with a jakarta.persistence import.
#
# Usage:
#   scripts/verify_migration.sh <path-to-src-root>
#
# Output (stdout): tab-separated rows describing each verification finding:
#   ok\tno-stray-javax\t<count=0>
#   ok\tjakarta-present\t<file-count>
#   fail\tstray-javax\t<file>:<line>\t<import>
#   fail\tentity-without-jakarta\t<file>
#   warn\tno-jpa-entities-found\t<src-root>
#
# Exit 0 if all checks pass (no `fail` rows). Exit 2 if any check fails.
# Exit 1 on usage error.

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path-to-src-root>" >&2
  exit 1
fi

ROOT="$1"
if [[ ! -d "$ROOT" ]]; then
  echo "error: not a directory: $ROOT" >&2
  exit 1
fi

GREP=${GREP:-grep}
failures=0

# 1. No stray migration-candidate javax imports.
stray=$("$GREP" -rEnH --include='*.java' \
  -e '^[[:space:]]*import[[:space:]]+javax\.(persistence|validation|servlet|annotation|transaction|ws\.rs|mail|jms|xml\.bind|inject|enterprise|ejb|json|batch)\b' \
  "$ROOT" 2>/dev/null || true)

if [[ -z "$stray" ]]; then
  printf "ok\tno-stray-javax\t0\n"
else
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    file=${line%%:*}
    rest=${line#*:}
    lineno=${rest%%:*}
    content=${rest#*:}
    # Trim leading whitespace from content.
    content=${content#"${content%%[![:space:]]*}"}
    printf "fail\tstray-javax\t%s:%s\t%s\n" "$file" "$lineno" "$content"
    failures=$((failures + 1))
  done <<< "$stray"
fi

# 2/3. Entity classes (look for @Entity annotation) must import jakarta.persistence.
entity_files=$("$GREP" -rlE '@Entity\b' --include='*.java' "$ROOT" 2>/dev/null || true)

if [[ -z "$entity_files" ]]; then
  printf "warn\tno-jpa-entities-found\t%s\n" "$ROOT"
else
  jakarta_persistence_count=0
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    if "$GREP" -qE '^[[:space:]]*import[[:space:]]+jakarta\.persistence\b' "$file"; then
      jakarta_persistence_count=$((jakarta_persistence_count + 1))
    else
      printf "fail\tentity-without-jakarta\t%s\n" "$file"
      failures=$((failures + 1))
    fi
  done <<< "$entity_files"
  printf "ok\tjakarta-present\t%s\n" "$jakarta_persistence_count"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "verify: $failures failure(s)" >&2
  exit 2
fi
echo "verify: all checks passed" >&2
exit 0
