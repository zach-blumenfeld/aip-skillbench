#!/usr/bin/env bash
# Smoke-train the GRPO setup at /app for a small number of steps and
# surface the metrics that matter for bug diagnosis.
#
# Usage:
#   bash scripts/smoke_train.sh           # default: 10 steps
#   bash scripts/smoke_train.sh 30        # 30 steps
#
# Reads /app/train_grpo.py and runs it with environment overrides so the
# training script itself is NOT modified. Output is written to
# /tmp/grpo-smoke-<timestamp>/ and the last ~20 log lines are printed.
#
# Expects: torch, transformers, trl installed; /app/train_grpo.py exists.

set -euo pipefail

MAX_STEPS="${1:-10}"
TS="$(date +%s)"
OUT="/tmp/grpo-smoke-${TS}"
mkdir -p "$OUT"

echo "=== smoke_train: max_steps=${MAX_STEPS}, output=${OUT} ==="

echo "--- verifying trl install resolves to /app/trl ---"
TRL_PATH="$(python -c 'import trl, os; print(os.path.dirname(trl.__file__))' 2>/dev/null || echo "NOT_INSTALLED")"
echo "trl resolves to: ${TRL_PATH}"
if [[ "$TRL_PATH" != /app/trl* ]]; then
  echo "WARNING: trl is NOT resolving to /app/trl — edits there will be invisible."
  echo "         Run: pip install -e /app/trl --force-reinstall --no-deps"
fi

echo "--- launching training (capped to ${MAX_STEPS} steps) ---"
# Common knobs the TRL HF Trainer respects via env / CLI. The training
# script is unmodified — we override via env so MAX_STEPS and OUTPUT_DIR
# bypass the script's defaults if it reads them, otherwise the CLI args
# below take effect.
export GRPO_MAX_STEPS="${MAX_STEPS}"
export GRPO_OUTPUT_DIR="${OUT}"

# Run the training script. If /app/train_grpo.py takes argparse flags,
# the second invocation form will work; if not, the first will. We try
# the no-args form first since most TRL scripts read their config inline.
LOG="${OUT}/train.log"
(
  cd /app
  set +e
  python train_grpo.py 2>&1 | tee "${LOG}"
  rc=${PIPESTATUS[0]}
  echo "(training exited with rc=${rc})"
) || true

echo
echo "--- last 30 log lines ---"
tail -n 30 "${LOG}" || true

echo
echo "--- searching log for GRPO diagnostic metrics ---"
grep -E "reward(_std)?|loss|kl|completion_length|advantage" "${LOG}" | tail -n 40 || \
  echo "(no GRPO metric lines found — check the training script's logger)"

echo
echo "=== smoke_train done. Full log: ${LOG} ==="
echo
echo "Healthy signal:"
echo "  - reward_std > 0 within a few steps"
echo "  - loss finite and non-zero (typical 1e-3 to 1.0)"
echo "  - kl small but non-zero (1e-4 to 1e-1)"
echo "  - mean reward begins trending upward by ~step 15-20"
echo "Broken signal:"
echo "  - reward_std == 0 every step       -> advantage normalization regression"
echo "  - loss == 0.0 every step           -> completion mask or no_grad bug"
echo "  - loss == NaN/Inf                  -> missing eps in std denom, or overflow"
echo "  - reward varies but mean reward never moves -> sign flip or grad disconnected"
