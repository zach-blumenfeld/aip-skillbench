#!/usr/bin/env bash
# Quick rule-syntax check via `suricata -T` (test mode).
#
# Exits 0 if Suricata reports the config + rules load cleanly, 1 otherwise.
# Both stdout and stderr from Suricata are forwarded so parse errors are
# visible to the agent — they typically name the line number and the
# offending option.
set -euo pipefail

rules="${1:-/root/local.rules}"
config="${2:-/root/suricata.yaml}"

if ! suricata -T -c "$config" -S "$rules" 2>&1; then
  echo "Suricata rejected the rules file. Fix the parse error above before re-running on PCAPs." >&2
  exit 1
fi

echo "Rule syntax OK."
