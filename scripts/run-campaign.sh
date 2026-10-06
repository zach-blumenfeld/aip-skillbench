#!/usr/bin/env bash
# Run one campaign collection (docs/campaigns.md) and print its summary.
#
#   bash scripts/run-campaign.sh <1|5|10|27> [extra run-matrix flags]
#
# Output goes to runs/campaign-N-<YYYY-MM-DD>/ (set CAMPAIGN_OUT to pick the directory,
# e.g. to resume a campaign started on an earlier day). Re-running resumes: cells already
# in summary.jsonl are skipped. Packs must exist first: scripts/compile-collection.sh N.
set -uo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

n="${1:-}"
case "$n" in
  1|5|10|27) shift ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 2 ;;
esac
for a in "$@"; do
  case "$a" in -h|--help) usage; exit 0 ;; esac
done

out="${CAMPAIGN_OUT:-runs/campaign-$n-$(date +%F)}"
keepawake=()
command -v caffeinate >/dev/null && keepawake=(caffeinate -dimsu)

${keepawake[@]+"${keepawake[@]}"} uv run aip-skillbench run-matrix \
  --config "configs/campaign-$n.yaml" --out "$out" --yes "$@"
rc=$?

uv run python scripts/campaign.py report "$out"
exit $rc
