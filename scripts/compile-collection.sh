#!/usr/bin/env bash
# Compile the AIP packs for one campaign collection (docs/campaigns.md).
#
#   bash scripts/compile-collection.sh <1|5|10|27> [--force] [--yes] [--dry-run]
#
# Authors one --single pack per task with Opus (`batch-convert --from curated`), only for
# tasks whose pack is missing or fails validation (every task with --force), then runs the
# validation sweep and the _authoring audit check over the whole collection.
# --dry-run prints the batch-convert command and spends nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

n="${1:-}"
case "$n" in
  1|5|10|27) shift ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 2 ;;
esac
force="" yes="" dry=""
for a in "$@"; do
  case "$a" in
    --force) force="--force" ;;
    --yes|-y) yes=1 ;;
    --dry-run) dry=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $a" >&2; usage; exit 2 ;;
  esac
done

todo="$(uv run python scripts/campaign.py to-compile "$n" $force)"
total="$(uv run python scripts/campaign.py tasks "$n" | wc -l | tr -d ' ')"
if [ -z "$todo" ] && [ -n "$dry" ]; then
  echo "campaign-$n: all $total packs present and valid; nothing to compile."
  echo "With --force it would recompile every task:"
  todo="$(uv run python scripts/campaign.py to-compile "$n" --force)"
  force="--force"
fi
if [ -z "$todo" ]; then
  echo "campaign-$n: all $total packs present and valid; nothing to compile."
else
  count="$(printf '%s\n' "$todo" | wc -l | tr -d ' ')"
  echo "campaign-$n: $count of $total tasks to compile:"
  printf '%s\n' "$todo" | sed 's/^/  /'
  # An existing pack that fails validation must be overwritten, so it needs --force too.
  if printf '%s\n' "$todo" | grep -q $'\tinvalid$'; then force="--force"; fi
  cmd=(uv run aip-skillbench batch-convert)
  while IFS=$'\t' read -r task _; do cmd+=(--task "$task"); done <<< "$todo"
  cmd+=(--from curated --single --concurrency 5 --yes)
  if [ -n "$force" ]; then cmd+=(--force); fi
  echo "Estimated spend: $count task(s) x \$2-4 (Opus) = \$$((count * 2))-$((count * 4)), ~10-15 min per wave of 5."
  echo "+ ${cmd[*]}"
  if [ -n "$dry" ]; then echo "(dry run: nothing spent)"; exit 0; fi
  if [ -z "$yes" ]; then
    echo "Starting in 5s. Ctrl-C to abort."; sleep 5
  fi
  "${cmd[@]}"
fi

echo
echo "Validation sweep and _authoring audit:"
uv run python scripts/campaign.py check "$n"
