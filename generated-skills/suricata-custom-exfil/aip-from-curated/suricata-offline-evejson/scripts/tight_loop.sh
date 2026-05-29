#!/usr/bin/env bash
# Tight feedback loop: validate rule syntax, then run Suricata offline on a
# positive PCAP (must alert with the target sid) and a negative PCAP (must
# not alert with the target sid). Emits a single combined summary.
#
# Usage:
#   tight_loop.sh <target_sid> [rules_path] [pos_pcap] [neg_pcap] [config_path]
#
# Defaults match the suricata-custom-exfil task layout:
#   rules_path   = /root/local.rules
#   pos_pcap     = /root/pcaps/train_pos.pcap
#   neg_pcap     = /root/pcaps/train_neg.pcap
#   config_path  = /root/suricata.yaml
#
# Exit codes:
#   0  positive PCAP fired target_sid AND negative PCAP did not.
#   1  syntax check failed, or Suricata produced no eve.json.
#   2  expectation mismatch (positive silent, or negative fired target_sid).
set -euo pipefail

target_sid="${1:-}"
if [[ -z "$target_sid" ]]; then
  echo "Usage: $0 <target_sid> [rules_path] [pos_pcap] [neg_pcap] [config_path]" >&2
  exit 2
fi

rules="${2:-/root/local.rules}"
pos_pcap="${3:-/root/pcaps/train_pos.pcap}"
neg_pcap="${4:-/root/pcaps/train_neg.pcap}"
config="${5:-/root/suricata.yaml}"

pos_log="/tmp/suri-pos"
neg_log="/tmp/suri-neg"

# 1. Syntax check.
echo "== suricata -T (syntax check) =="
if ! suricata -T -c "$config" -S "$rules" 2>&1; then
  echo "Syntax check failed. Fix rule parse errors before re-running." >&2
  exit 1
fi

run_one() {
  local pcap="$1" log_dir="$2" label="$3"
  echo
  echo "== $label : $pcap =="
  rm -rf "$log_dir"
  mkdir -p "$log_dir"
  suricata -c "$config" -S "$rules" -k none -r "$pcap" -l "$log_dir" >/dev/null 2>&1 || true
  if [[ ! -f "$log_dir/eve.json" ]]; then
    echo "No eve.json produced for $pcap." >&2
    return 1
  fi
  echo "Alerts (signature_id -> count):"
  jq -r 'select(.event_type=="alert") | .alert.signature_id' "$log_dir/eve.json" \
    | sort -n \
    | uniq -c \
    | awk '{print "  "$2"\t"$1}'
}

run_one "$pos_pcap" "$pos_log" "POSITIVE" || exit 1
run_one "$neg_pcap" "$neg_log" "NEGATIVE" || exit 1

pos_count=$(jq -r --argjson sid "$target_sid" \
  'select(.event_type=="alert" and .alert.signature_id==$sid) | .alert.signature_id' \
  "$pos_log/eve.json" | wc -l | tr -d ' ')
neg_count=$(jq -r --argjson sid "$target_sid" \
  'select(.event_type=="alert" and .alert.signature_id==$sid) | .alert.signature_id' \
  "$neg_log/eve.json" | wc -l | tr -d ' ')

echo
echo "== verdict (target sid: $target_sid) =="
echo "  positive PCAP fired sid $target_sid : $pos_count time(s) (want: >=1)"
echo "  negative PCAP fired sid $target_sid : $neg_count time(s) (want: 0)"

if [[ "$pos_count" -ge 1 && "$neg_count" -eq 0 ]]; then
  echo "PASS"
  exit 0
fi

if [[ "$pos_count" -lt 1 ]]; then
  echo "FAIL: positive PCAP did not fire target sid — rule is under-matching. Loosen one constraint at a time and re-run." >&2
fi
if [[ "$neg_count" -ne 0 ]]; then
  echo "FAIL: negative PCAP fired target sid — rule is over-matching. Tighten the constraint that the negative traffic violates." >&2
fi
exit 2
