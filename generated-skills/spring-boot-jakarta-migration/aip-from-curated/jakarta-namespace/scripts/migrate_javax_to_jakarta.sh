#!/usr/bin/env bash
# Rewrite migration-candidate `javax.*` imports to `jakarta.*` across a Java
# source tree. Deterministic sed replacement — same prefixes the inventory
# script flags, same exclusions. JDK-internal packages (javax.sql, javax.crypto,
# javax.net, javax.security, javax.naming, javax.management, javax.xml.*
# excluding javax.xml.bind) are NOT touched.
#
# Usage:
#   scripts/migrate_javax_to_jakarta.sh <path-to-src-root> [--dry-run]
#
# Output (stdout): one line per rewritten file, tab-separated:
#   <file>\t<replacements>
# stderr carries a one-line totals summary.
#
# Exit 0 on success (including zero changes). Exit 1 on usage error.
#
# Notes:
# - GNU sed and BSD/macOS sed both honor `sed -i.bak ...` then we delete the
#   `.bak` files. Plain `-i` is not portable across the two.
# - Wildcard imports (`javax.persistence.*`) are covered because the prefix
#   match `javax.persistence` rewrites both `javax.persistence.Entity` and
#   `javax.persistence.*`.
# - Only `import` lines are rewritten. Fully-qualified usages elsewhere in
#   source are rare; if the inventory surfaces them, fix manually with Edit.

set -euo pipefail

DRY_RUN=0
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <path-to-src-root> [--dry-run]" >&2
  exit 1
fi
ROOT="$1"
if [[ $# -eq 2 ]]; then
  if [[ "$2" != "--dry-run" ]]; then
    echo "usage: $0 <path-to-src-root> [--dry-run]" >&2
    exit 1
  fi
  DRY_RUN=1
fi
if [[ ! -d "$ROOT" ]]; then
  echo "error: not a directory: $ROOT" >&2
  exit 1
fi

# Prefixes to rewrite. Order matters only insofar as longer/more-specific
# prefixes (e.g., `javax.xml.bind`) must precede shorter ones (`javax.xml`) —
# here there's no shorter `javax.xml` prefix in the list, so order is free.
PREFIXES=(
  "javax.persistence"
  "javax.validation"
  "javax.servlet"
  "javax.annotation"
  "javax.transaction"
  "javax.ws.rs"
  "javax.mail"
  "javax.jms"
  "javax.xml.bind"
  "javax.inject"
  "javax.enterprise"
  "javax.ejb"
  "javax.json"
  "javax.batch"
)

# Files containing any migration-candidate import. Restrict to *.java.
candidates=$(find "$ROOT" -name '*.java' -type f -print0 \
  | xargs -0 grep -lE '^[[:space:]]*import[[:space:]]+javax\.(persistence|validation|servlet|annotation|transaction|ws\.rs|mail|jms|xml\.bind|inject|enterprise|ejb|json|batch)\b' 2>/dev/null || true)

if [[ -z "$candidates" ]]; then
  echo "no migration-candidate imports under: $ROOT" >&2
  exit 0
fi

total_files=0
total_repls=0

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  # Build a single sed program covering every prefix; count replacements after.
  sed_args=()
  for pfx in "${PREFIXES[@]}"; do
    # Escape dots in the source prefix for the regex.
    src_re=$(printf '%s' "$pfx" | sed 's/\./\\./g')
    dst=${pfx/#javax./jakarta.}
    sed_args+=( -e "s|^\([[:space:]]*\)import[[:space:]]\{1,\}${src_re}|\1import ${dst}|" )
  done

  if [[ "$DRY_RUN" -eq 1 ]]; then
    # Count would-be replacements without writing.
    before=$(grep -cE '^[[:space:]]*import[[:space:]]+javax\.(persistence|validation|servlet|annotation|transaction|ws\.rs|mail|jms|xml\.bind|inject|enterprise|ejb|json|batch)\b' "$file" || true)
    printf "%s\t%s\n" "$file" "$before"
    total_files=$((total_files + 1))
    total_repls=$((total_repls + before))
    continue
  fi

  before=$(grep -cE '^[[:space:]]*import[[:space:]]+javax\.(persistence|validation|servlet|annotation|transaction|ws\.rs|mail|jms|xml\.bind|inject|enterprise|ejb|json|batch)\b' "$file" || true)
  sed -i.bak "${sed_args[@]}" "$file"
  rm -f "$file.bak"
  after=$(grep -cE '^[[:space:]]*import[[:space:]]+javax\.(persistence|validation|servlet|annotation|transaction|ws\.rs|mail|jms|xml\.bind|inject|enterprise|ejb|json|batch)\b' "$file" || true)
  repls=$((before - after))
  printf "%s\t%s\n" "$file" "$repls"
  total_files=$((total_files + 1))
  total_repls=$((total_repls + repls))
done <<< "$candidates"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry-run: $total_files file(s), $total_repls candidate import(s)" >&2
else
  echo "rewrote: $total_files file(s), $total_repls import(s)" >&2
fi
