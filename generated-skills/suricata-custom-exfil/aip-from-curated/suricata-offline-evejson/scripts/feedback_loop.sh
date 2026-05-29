#!/usr/bin/env bash
# Tight iteration loop for Suricata offline rule development.
# 1) Validates rule syntax with `suricata -T`.
# 2) Runs the rules against a known-positive pcap; prints sid -> count.
# 3) Runs the rules against a known-negative pcap; prints sid -> count.
#
# Usage:
#   feedback_loop.sh <pos_pcap> <neg_pcap> [rules_path] [config_path] [log_root]
#
# Exit codes:
#   0  rule syntax OK and both runs produced eve.json
#   2  bad arguments
#   3  rule syntax check failed
#   4  positive run produced no eve.json
#   5  negative run produced no eve.json

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <pos_pcap> <neg_pcap> [rules_path] [config_path] [log_root]" >&2
  exit 2
fi

pos_pcap="$1"
neg_pcap="$2"
rules="${3:-/root/local.rules}"
config="${4:-/root/suricata.yaml}"
log_root="${5:-/tmp}"

pos_dir="$log_root/suri-pos"
neg_dir="$log_root/suri-neg"

echo "== Step 1: rule syntax check =="
if ! suricata -T -c "$config" -S "$rules"; then
  echo "Rule syntax check failed. Fix rules at $rules before rerunning." >&2
  exit 3
fi

run_one() {
  local pcap="$1" out_dir="$2" label="$3"
  rm -rf "$out_dir"
  mkdir -p "$out_dir"
  suricata -c "$config" -S "$rules" -k none -r "$pcap" -l "$out_dir" >/dev/null 2>&1 || true
  if [[ ! -f "$out_dir/eve.json" ]]; then
    echo "No eve.json from $label run at $out_dir" >&2
    return 1
  fi
  echo "-- $label alerts (signature_id -> count) --"
  jq -r 'select(.event_type=="alert") | .alert.signature_id' "$out_dir/eve.json" \
    | sort -n \
    | uniq -c \
    | awk '{print $2"\t"$1}'
}

echo "== Step 2: positive pcap ($pos_pcap) =="
run_one "$pos_pcap" "$pos_dir" "positive" || exit 4

echo "== Step 3: negative pcap ($neg_pcap) =="
run_one "$neg_pcap" "$neg_dir" "negative" || exit 5

echo "== Done. Inspect $pos_dir/eve.json and $neg_dir/eve.json for full alert detail =="
