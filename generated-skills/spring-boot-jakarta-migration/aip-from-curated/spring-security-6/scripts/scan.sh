#!/usr/bin/env bash
# Scan a Java project for Spring Security 5 patterns that must change for Spring Security 6.
# Usage: scan.sh [project-root]   (defaults to the current directory)
#
# Emits a single JSON-ish report on stdout listing, for each deprecated pattern,
# the files (and counts) that contain it. Exits 0 always — discovery is not a failure.

set -euo pipefail

ROOT="${1:-.}"

if [ ! -d "$ROOT" ]; then
  echo "scan.sh: project root not found: $ROOT" >&2
  exit 2
fi

# Each entry: label|pattern (fixed string, not regex)
PATTERNS=(
  "websecurityconfigureradapter|extends WebSecurityConfigurerAdapter"
  "enable_global_method_security|@EnableGlobalMethodSecurity"
  "ant_matchers|.antMatchers("
  "mvc_matchers|.mvcMatchers("
  "regex_matchers|.regexMatchers("
  "authorize_requests|.authorizeRequests("
  "javax_servlet_import|import javax.servlet."
  "authentication_manager_bean_override|authenticationManagerBean()"
)

echo "{"
echo "  \"root\": \"$ROOT\","
echo "  \"findings\": ["
first=1
for entry in "${PATTERNS[@]}"; do
  label="${entry%%|*}"
  pattern="${entry#*|}"
  # -F = fixed string, -l = list filenames, --include limits to Java sources.
  files=$(grep -rlF --include="*.java" -- "$pattern" "$ROOT" 2>/dev/null || true)
  count=0
  if [ -n "$files" ]; then
    count=$(printf '%s\n' "$files" | wc -l | tr -d ' ')
  fi
  if [ "$first" -eq 0 ]; then echo "    ,"; fi
  first=0
  echo "    {"
  echo "      \"label\": \"$label\","
  echo "      \"pattern\": \"$(printf '%s' "$pattern" | sed 's/"/\\"/g')\","
  echo "      \"file_count\": $count,"
  if [ "$count" -gt 0 ]; then
    echo "      \"files\": ["
    fi_first=1
    while IFS= read -r f; do
      if [ "$fi_first" -eq 0 ]; then echo "        ,"; fi
      fi_first=0
      echo "        \"$f\""
    done <<< "$files"
    echo "      ]"
  else
    echo "      \"files\": []"
  fi
  echo "    }"
done
echo "  ]"
echo "}"
