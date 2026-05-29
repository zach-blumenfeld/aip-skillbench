#!/usr/bin/env bash
# Verify that a Java project no longer contains Spring Security 5 patterns
# and (when appropriate) contains the Spring Security 6 replacements.
#
# Usage: verify.sh [project-root]   (defaults to current directory)
#
# Exit 0  -> verification passed (no deprecated patterns remaining).
# Exit 1  -> at least one deprecated pattern remains; details on stdout.
# Exit 2  -> usage error (bad root).
#
# A presence check is also performed for the *new* patterns. The presence
# check is informational only — it does not flip the exit code, because a
# project may legitimately have no method-level security (no @EnableMethodSecurity
# expected) or no security config at all.

set -euo pipefail

ROOT="${1:-.}"

if [ ! -d "$ROOT" ]; then
  echo "verify.sh: project root not found: $ROOT" >&2
  exit 2
fi

# Must-be-absent patterns (label | fixed-string pattern)
DEPRECATED=(
  "WebSecurityConfigurerAdapter|WebSecurityConfigurerAdapter"
  "@EnableGlobalMethodSecurity|@EnableGlobalMethodSecurity"
  ".antMatchers(|.antMatchers("
  ".mvcMatchers(|.mvcMatchers("
  ".regexMatchers(|.regexMatchers("
  ".authorizeRequests(|.authorizeRequests("
)

# Should-be-present patterns (informational only)
EXPECTED=(
  "SecurityFilterChain|SecurityFilterChain"
  ".requestMatchers(|.requestMatchers("
  ".authorizeHttpRequests(|.authorizeHttpRequests("
)

status=0
echo "== Deprecated pattern check (must be empty) =="
for entry in "${DEPRECATED[@]}"; do
  label="${entry%%|*}"
  pat="${entry#*|}"
  hits=$(grep -rlF --include="*.java" -- "$pat" "$ROOT" 2>/dev/null || true)
  if [ -n "$hits" ]; then
    status=1
    count=$(printf '%s\n' "$hits" | wc -l | tr -d ' ')
    echo "  FAIL  $label  ($count file(s))"
    printf '%s\n' "$hits" | sed 's/^/        /'
  else
    echo "  ok    $label"
  fi
done

echo
echo "== Expected pattern check (informational) =="
for entry in "${EXPECTED[@]}"; do
  label="${entry%%|*}"
  pat="${entry#*|}"
  hits=$(grep -rlF --include="*.java" -- "$pat" "$ROOT" 2>/dev/null || true)
  if [ -n "$hits" ]; then
    count=$(printf '%s\n' "$hits" | wc -l | tr -d ' ')
    echo "  present  $label  ($count file(s))"
  else
    echo "  absent   $label"
  fi
done

exit $status
