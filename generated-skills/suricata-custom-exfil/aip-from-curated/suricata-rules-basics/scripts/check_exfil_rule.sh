#!/usr/bin/env bash
# check_exfil_rule.sh — lint a candidate Suricata rule against the five
# conditions of the suricata-custom-exfil task.
#
# Usage:
#   check_exfil_rule.sh <rules-file> [sid]
#
# Default sid is 1000001 (the task contract).
#
# Exit codes:
#   0  all five conditions present
#   1  one or more conditions missing (prints checklist on stderr)
#   2  bad invocation / file unreadable

set -u

RULES_FILE="${1:-}"
SID="${2:-1000001}"

if [[ -z "${RULES_FILE}" ]]; then
  echo "usage: $(basename "$0") <rules-file> [sid]" >&2
  exit 2
fi
if [[ ! -r "${RULES_FILE}" ]]; then
  echo "error: cannot read ${RULES_FILE}" >&2
  exit 2
fi

# Extract the single rule whose sid matches. A Suricata rule may span lines;
# normalise to one line so subsequent grep/regex checks are predictable.
RULE_ONE_LINE="$(
  awk -v RS='' '{gsub(/\n[ \t]*/, " "); print}' "${RULES_FILE}" \
    | grep -E "sid[[:space:]]*:[[:space:]]*${SID}\b" \
    | head -n 1
)"

if [[ -z "${RULE_ONE_LINE}" ]]; then
  echo "error: no rule with sid:${SID} found in ${RULES_FILE}" >&2
  exit 1
fi

fail=0
check() {
  local label="$1" pattern="$2"
  if echo "${RULE_ONE_LINE}" | grep -Eq "${pattern}"; then
    echo "  [ok]   ${label}"
  else
    echo "  [miss] ${label}" >&2
    fail=1
  fi
}

echo "Linting sid:${SID} in ${RULES_FILE}"

# 1. HTTP POST scoped to http.method (not bare content match).
check "http.method buffer is used" \
  'http\.method[[:space:]]*;'
check "POST literal matched after http.method" \
  'http\.method[[:space:]]*;[[:space:]]*content[[:space:]]*:[[:space:]]*"POST"'

# 2. Exact URI /telemetry/v2/report under http.uri.
check "http.uri buffer is used" \
  'http\.uri[[:space:]]*;'
check "URI /telemetry/v2/report matched under http.uri" \
  'http\.uri[[:space:]]*;[[:space:]]*content[[:space:]]*:[[:space:]]*"/telemetry/v2/report"'

# 3. Header X-TLM-Mode: exfil under http.header. `:` is conventionally
#    hex-escaped as |3a|, so accept either form.
check "http.header buffer is used" \
  'http\.header[[:space:]]*;'
check "X-TLM-Mode: exfil header constraint present" \
  'http\.header[[:space:]]*;[[:space:]]*content[[:space:]]*:[[:space:]]*"X-TLM-Mode(\\:|\|3a\|)[[:space:]]?exfil"'

# 4. http_client_body covers blob= with a length-bounded Base64-ish PCRE.
check "http_client_body buffer is used" \
  'http_client_body[[:space:]]*;'
check "blob= literal present in body" \
  'http_client_body[[:space:]]*;[[:space:]]*content[[:space:]]*:[[:space:]]*"blob="'
check "blob= PCRE with length >= 80 Base64-ish chars" \
  'pcre[[:space:]]*:[[:space:]]*"/blob=\[A-Za-z0-9\+(\\)?/\]\{80,\}/"?'

# 5. sig= with exactly 64 hex chars under http_client_body.
check "sig= literal present in body" \
  'http_client_body[[:space:]]*;[[:space:]]*content[[:space:]]*:[[:space:]]*"sig="'
check "sig= PCRE with exactly 64 hex chars" \
  'pcre[[:space:]]*:[[:space:]]*"/sig=\[0-9a-fA-F\]\{64\}/"?'

# Generic structural checks.
check "flow:established,to_server set" \
  'flow[[:space:]]*:[[:space:]]*established,to_server'
check "rule action is alert" \
  '^[[:space:]]*alert[[:space:]]+http'

if (( fail == 0 )); then
  echo "ok: sid:${SID} satisfies all five exfil conditions"
  exit 0
fi
echo "fail: sid:${SID} is missing one or more conditions (see [miss] lines above)" >&2
exit 1
