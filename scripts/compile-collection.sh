#!/usr/bin/env bash
# Compile the AIP packs for one campaign collection (docs/campaigns.md).
#
#   bash scripts/compile-collection.sh <1|5|10|27|ablation> --variant <V> [--force] [--yes] [--dry-run]
#
# Authors one pack per task under compile variant V (`batch-convert --variant V`), only for
# tasks whose V pack is missing or fails V's gate (every task with --force), then runs the
# gate sweep and the _authoring audit check over the whole collection.
# --dry-run prints the batch-convert command and spends nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

n="${1:-}"
case "$n" in
  1|5|10|27|ablation) shift ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 2 ;;
esac
force="" yes="" dry="" variant=""
while [ $# -gt 0 ]; do
  case "$1" in
    --variant) variant="${2:-}"; shift ;;
    --force) force="--force" ;;
    --yes|-y) yes=1 ;;
    --dry-run) dry=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $1" >&2; usage; exit 2 ;;
  esac
  shift
done
if [ -z "$variant" ]; then echo "--variant <name> is required" >&2; usage; exit 2; fi

todo="$(uv run python scripts/campaign.py to-compile "$n" --variant "$variant" $force)"
total="$(uv run python scripts/campaign.py tasks "$n" | wc -l | tr -d ' ')"
if [ -z "$todo" ] && [ -n "$dry" ]; then
  echo "campaign-$n ($variant): all $total packs present and valid; nothing to compile."
  echo "With --force it would recompile every task:"
  todo="$(uv run python scripts/campaign.py to-compile "$n" --variant "$variant" --force)"
  force="--force"
fi
if [ -z "$todo" ]; then
  echo "campaign-$n ($variant): all $total packs present and valid; nothing to compile."
else
  count="$(printf '%s\n' "$todo" | wc -l | tr -d ' ')"
  echo "campaign-$n ($variant): $count of $total tasks to compile:"
  printf '%s\n' "$todo" | sed 's/^/  /'
  # An existing pack that fails validation must be overwritten, so it needs --force too.
  if printf '%s\n' "$todo" | grep -q $'\tinvalid$'; then force="--force"; fi
  cmd=(uv run aip-skillbench batch-convert)
  while IFS=$'\t' read -r task _; do cmd+=(--task "$task"); done <<< "$todo"
  cmd+=(--variant "$variant" --concurrency 5 --yes)
  if [ -n "$force" ]; then cmd+=(--force); fi
  echo "Estimated spend: $count pack(s) x ~\$4 (Opus 5.5, measured mean \$4.19) = ~\$$((count * 4)), ~10-15 min per wave of 5."
  echo "+ ${cmd[*]}"
  if [ -n "$dry" ]; then echo "(dry run: nothing spent)"; exit 0; fi
  if [ -z "$yes" ]; then
    echo "Starting in 5s. Ctrl-C to abort."; sleep 5
  fi
  "${cmd[@]}"
fi

echo
echo "Gate sweep ($variant) and _authoring audit:"
uv run python scripts/campaign.py check "$n" --variant "$variant"
