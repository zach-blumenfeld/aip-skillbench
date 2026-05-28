#!/usr/bin/env python3
"""Check captured GRPO training metrics against correctness invariants.

The agent instruments the trainer (NOT train_grpo.py) to dump per-step summary
statistics to a JSON file, then runs this checker. It applies the numeric thresholds
and the invariant -> bug-category lookup so the diagnosis is consistent, and (in
--verify mode) decides whether the reward curve is actually improving.

Input JSON shape (all per-step fields optional; checks SKIP when data is absent):

    {
      "num_generations": 8,
      "steps": [
        {
          "step": 0,
          "loss": 0.12,
          "loss_requires_grad": true,
          "grad_norm": 0.0,
          "per_token_logps_requires_grad": true,
          "coef1_requires_grad": true,
          "coef1_mean": 1.0,
          "clip_fraction": 0.0,
          "advantages_abs_mean": 0.0,
          "advantages_std": 0.0,
          "within_group_adv_sum_absmax": 0.0,
          "reward_mean": 0.0,
          "reward_std": 0.3,
          "completion_mask_sum": 240,
          "completion_mask_total": 256,
          "kl_term_absmean": null,
          "policy_term_absmean": null
        }
      ]
    }

Usage:
    python3 grpo_invariants.py metrics.json            # diagnose a buggy run
    python3 grpo_invariants.py metrics.json --verify   # confirm reward improved after fix

Output contract:
    stdout : one human-readable line per check (PASS / FAIL / SKIP) + a summary.
    stderr : JSON Lines, one record per FAIL/WARN {"status","invariant","bug_category",...}.
    exit   : 0 if no FAIL, 1 if any FAIL.

Stdlib only; runs under `uv run` or plain `python3`.
"""
import argparse
import json
import sys

# Thresholds. Kept here (not in prose) so diagnosis is deterministic.
EPS_GRAD = 1e-10          # grad_norm at/below this == effectively no gradient
EPS_ADV = 1e-6            # advantages this small (abs mean) == effectively zero signal
EPS_REWARD_VAR = 1e-6     # reward_std above this means rewards varied -> advantages should too
GROUP_SUM_TOL = 1e-3      # within-group advantage sum should be ~0 (mean-centered)
CLIP_COLLAPSE = 0.99      # clip fraction at/above this == update collapsed
KL_DOMINATE = 10.0        # |kl term| / |policy term| above this == KL drowns reward signal
VERIFY_MIN_GAIN = 0.05    # last-third mean reward must beat first-third by this (relative-ish)


def emit(status, invariant, bug_category=None, **extra):
    rec = {"status": status, "invariant": invariant}
    if bug_category:
        rec["bug_category"] = bug_category
    rec.update(extra)
    print(json.dumps(rec), file=sys.stderr)


def has(step, *keys):
    return all(k in step and step[k] is not None for k in keys)


class Report:
    def __init__(self):
        self.failed = False

    def check(self, name, ok, msg, bug_category=None):
        if ok is None:
            print(f"SKIP  {name}: {msg}")
            return
        if ok:
            print(f"PASS  {name}: {msg}")
        else:
            tag = f"  [-> bug category {bug_category}]" if bug_category else ""
            print(f"FAIL  {name}: {msg}{tag}")
            emit("FAIL", name, bug_category=bug_category, detail=msg)
            self.failed = True


def diagnose(data, rep):
    steps = data.get("steps", [])
    if not steps:
        print("FAIL  input: no `steps` array in metrics JSON")
        emit("FAIL", "input", detail="no steps")
        rep.failed = True
        return

    # A. Gradient connectivity — any step with a dead gradient is fatal.
    grad_seen = [s for s in steps if has(s, "grad_norm")]
    if grad_seen:
        dead = [s for s in grad_seen if s["grad_norm"] <= EPS_GRAD]
        rep.check(
            "gradient-flows", len(dead) == 0,
            f"{len(dead)}/{len(grad_seen)} steps had grad_norm <= {EPS_GRAD}",
            bug_category="A",
        )
    else:
        rep.check("gradient-flows", None, "no grad_norm captured")

    for flag, label in (
        ("loss_requires_grad", "loss-requires-grad"),
        ("per_token_logps_requires_grad", "logps-requires-grad"),
        ("coef1_requires_grad", "ratio-requires-grad"),
    ):
        seen = [s for s in steps if has(s, flag)]
        if seen:
            bad = [s for s in seen if not s[flag]]
            rep.check(label, len(bad) == 0,
                      f"{len(bad)}/{len(seen)} steps had {flag} == False", bug_category="A")
        else:
            rep.check(label, None, f"no {flag} captured")

    # B. Advantages non-zero when rewards varied.
    adv_seen = [s for s in steps if has(s, "advantages_abs_mean")]
    if adv_seen:
        # Only judge steps where rewards actually varied (else 0 advantage is legitimate).
        judged = [s for s in adv_seen if not has(s, "reward_std") or s["reward_std"] > EPS_REWARD_VAR]
        zero = [s for s in judged if s["advantages_abs_mean"] <= EPS_ADV]
        if judged:
            rep.check("advantages-nonzero", len(zero) == 0,
                      f"{len(zero)}/{len(judged)} steps (with reward variation) had "
                      f"advantages_abs_mean <= {EPS_ADV}", bug_category="B")
        else:
            rep.check("advantages-nonzero", None,
                      "rewards never varied in captured steps — cannot judge advantages")
    else:
        rep.check("advantages-nonzero", None, "no advantages_abs_mean captured")

    # C. Within-group advantage centering (repeat vs repeat_interleave / view order).
    grp_seen = [s for s in steps if has(s, "within_group_adv_sum_absmax")]
    if grp_seen:
        bad = [s for s in grp_seen if s["within_group_adv_sum_absmax"] > GROUP_SUM_TOL]
        rep.check("group-centered", len(bad) == 0,
                  f"{len(bad)}/{len(grp_seen)} steps had within-group advantage sum > "
                  f"{GROUP_SUM_TOL} (groups scrambled?)", bug_category="C")
    else:
        rep.check("group-centered", None, "no within_group_adv_sum_absmax captured")

    # D. Completion mask non-empty.
    mask_seen = [s for s in steps if has(s, "completion_mask_sum")]
    if mask_seen:
        empty = [s for s in mask_seen if s["completion_mask_sum"] <= 0]
        rep.check("mask-nonempty", len(empty) == 0,
                  f"{len(empty)}/{len(mask_seen)} steps had completion_mask_sum <= 0",
                  bug_category="D")
    else:
        rep.check("mask-nonempty", None, "no completion_mask_sum captured")

    # H. Clip collapse.
    clip_seen = [s for s in steps if has(s, "clip_fraction")]
    if clip_seen:
        collapsed = [s for s in clip_seen if s["clip_fraction"] >= CLIP_COLLAPSE]
        rep.check("clip-not-collapsed", len(collapsed) == 0,
                  f"{len(collapsed)}/{len(clip_seen)} steps had clip_fraction >= {CLIP_COLLAPSE}",
                  bug_category="H")
    else:
        rep.check("clip-not-collapsed", None, "no clip_fraction captured")

    # G. KL domination.
    kl_seen = [s for s in steps if has(s, "kl_term_absmean", "policy_term_absmean")]
    if kl_seen:
        bad = [s for s in kl_seen
               if s["policy_term_absmean"] > 0
               and s["kl_term_absmean"] / s["policy_term_absmean"] >= KL_DOMINATE]
        rep.check("kl-not-dominating", len(bad) == 0,
                  f"{len(bad)}/{len(kl_seen)} steps had |KL| / |policy| >= {KL_DOMINATE}",
                  bug_category="G")
    else:
        rep.check("kl-not-dominating", None, "no kl/policy term magnitudes captured")


def verify_reward_trend(data, rep):
    steps = [s for s in data.get("steps", []) if "reward_mean" in s and s["reward_mean"] is not None]
    if len(steps) < 6:
        print("SKIP  reward-improving: need >= 6 steps with reward_mean to judge a trend")
        emit("WARN", "reward-improving", detail="insufficient steps")
        return
    n = len(steps)
    third = max(1, n // 3)
    first = [s["reward_mean"] for s in steps[:third]]
    last = [s["reward_mean"] for s in steps[-third:]]
    first_m = sum(first) / len(first)
    last_m = sum(last) / len(last)
    gain = last_m - first_m
    ok = gain > VERIFY_MIN_GAIN
    rep.check("reward-improving", ok,
              f"first-third mean={first_m:.4f}, last-third mean={last_m:.4f}, "
              f"gain={gain:+.4f} (need > {VERIFY_MIN_GAIN})")


def main():
    ap = argparse.ArgumentParser(description="Check GRPO metrics against correctness invariants.")
    ap.add_argument("metrics", help="Path to metrics JSON.")
    ap.add_argument("--verify", action="store_true",
                    help="Post-fix mode: also require the reward curve to be improving.")
    args = ap.parse_args()

    try:
        with open(args.metrics) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL  could not read metrics JSON: {e}")
        emit("FAIL", "input", detail=str(e))
        return 1

    rep = Report()
    print("=" * 60)
    print("GRPO invariant check" + ("  (verify mode)" if args.verify else ""))
    print("=" * 60)
    diagnose(data, rep)
    if args.verify:
        verify_reward_trend(data, rep)

    print("-" * 60)
    if rep.failed:
        print("RESULT: FAIL — see flagged invariant(s); cross-reference references/grpo-bug-catalog.md")
        return 1
    print("RESULT: PASS — no invariant violated"
          + (" and reward is improving" if args.verify else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
