#!/usr/bin/env bash
# Apply the deterministic Spring Security 5 -> 6 textual replacements across a
# Java project. Idempotent: re-running on an already-migrated tree is a no-op.
# Uses `perl -i` for portability (works under BSD and GNU userland alike).
#
# Usage: mechanical_renames.sh [project-root]   (defaults to current directory)
#
# Replacements applied:
#   1.  @EnableGlobalMethodSecurity          -> @EnableMethodSecurity
#   2.  EnableGlobalMethodSecurity (import)  -> EnableMethodSecurity
#   3.  .antMatchers(                        -> .requestMatchers(
#   4.  .mvcMatchers(                        -> .requestMatchers(
#   5.  .regexMatchers(                      -> .requestMatchers(
#   6.  .authorizeRequests(                  -> .authorizeHttpRequests(
#
# Replacements deliberately NOT applied here (require reasoning, not text sub):
#   - WebSecurityConfigurerAdapter removal: the class body must be refactored
#     to a SecurityFilterChain @Bean. Handle in the `refactor-config-class`
#     step instead.
#   - Lambda DSL conversion (chained .csrf().disable().and() -> csrf -> csrf.disable()):
#     the structural rewrite is too fragile for blind sed. Handle in the
#     `convert-lambda-dsl` step.
#   - javax.servlet -> jakarta.servlet: this is the Jakarta EE migration's
#     responsibility, not Spring Security's. Run the jakarta migration skill.

set -euo pipefail

ROOT="${1:-.}"

if [ ! -d "$ROOT" ]; then
  echo "mechanical_renames.sh: project root not found: $ROOT" >&2
  exit 2
fi

# Count and process Java files. Portable across bash 3.2 (macOS default) and
# bash 4+ — avoids mapfile / readarray. `find -exec` streams files to perl in
# batches, so very large trees work without building a huge argv.
count=$(find "$ROOT" -type f -name "*.java" | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then
  echo "mechanical_renames.sh: no .java files under $ROOT" >&2
  exit 0
fi

# Apply replacements. perl is preferred over sed because `sed -i` differs
# between BSD (macOS) and GNU (Linux); perl's -i is consistent everywhere.
find "$ROOT" -type f -name "*.java" -exec perl -i -pe '
  s/\@EnableGlobalMethodSecurity\b/\@EnableMethodSecurity/g;
  s/\bEnableGlobalMethodSecurity\b/EnableMethodSecurity/g;
  s/\.antMatchers\(/.requestMatchers(/g;
  s/\.mvcMatchers\(/.requestMatchers(/g;
  s/\.regexMatchers\(/.requestMatchers(/g;
  s/\.authorizeRequests\(/.authorizeHttpRequests(/g;
' {} +

echo "mechanical_renames.sh: applied to ${count} Java file(s) under $ROOT"
