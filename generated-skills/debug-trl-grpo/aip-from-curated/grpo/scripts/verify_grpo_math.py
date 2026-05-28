"""Check a GRPO implementation against the algorithm specification.

Run with:
    python verify_grpo_math.py [path/to/grpo_trainer.py]

This script does NOT decide whether a training run will improve. It evaluates
the three GRPO computations that have exact, input-independent invariants and
prints what the implementation produces on small fixed inputs so you can
compare against the spec in the grpo skill (SKILL.md / references/):

  1. Per-token log-probability  (log_pi(t) = logit(t) - logsumexp(logits))
       invariant: log_pi <= 0 always; must match F.log_softmax; the dominant
       token's log-prob is close to 0, not close to the minimum.
  2. Group-relative advantage   (A_i = (r_i - mean) / (std + epsilon))
       invariant: epsilon is a tiny numerical-stability constant (1e-8..1e-4),
       NOT large; advantages are mean-centered per group and non-zero when
       rewards vary; ~0 only when rewards in a group are constant.
  3. Decode / strip             (text the reward function scores)
       invariant: every completion shape survives with non-empty output where
       a human expects non-empty output; only a genuinely unfinished reasoning
       block (opened, never closed) is allowed to blank.

The script exits non-zero only on unambiguous violations (e.g. a positive
log-prob, or an additive advantage epsilon >= 1). Borderline results are
printed with a `?` marker so you notice them without short-circuiting the run.

Edit the adapters below to point at your implementation. Defaults target TRL.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Callable

import torch
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Project adapters — edit to point at your implementation. Defaults: TRL.
# ---------------------------------------------------------------------------

def load_log_softmax_fn() -> Callable:
    """(logits, index) -> per-token log-probs of the selected tokens."""
    from trl.trainer.utils import selective_log_softmax
    return selective_log_softmax


def load_decode_fn() -> Callable:
    """(input_ids, tokenizer) -> list[str] of decoded, stripped completions."""
    from trl.trainer.utils import decode_and_strip_padding
    return decode_and_strip_padding


def locate_advantage_source() -> str | None:
    """Path to the file containing the advantage-normalization line.

    Defaults to TRL's grpo_trainer.py. Override by passing a path on argv, or
    edit this function. Return None to skip the epsilon-source scan.
    """
    try:
        import trl
        path = os.path.join(os.path.dirname(trl.__file__), "trainer", "grpo_trainer.py")
        return path if os.path.exists(path) else None
    except Exception:
        return None


def load_tokenizer():
    """Tokenizer for the decode round-trip. Any tokenizer works for the shape
    test; the default is small and offline-friendly."""
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained("gpt2")


# ---------------------------------------------------------------------------
# Reporting helpers.
# ---------------------------------------------------------------------------

_hard_failures: list[str] = []


def _section(title: str) -> None:
    print(f"\n--- {title} ---")


def _kv(label: str, value, flag: str = "") -> None:
    marker = f" {flag}" if flag else ""
    print(f"  {label}: {value}{marker}")


def _fail(check: str, msg: str) -> None:
    print(f"  !! {check}: {msg}")
    _hard_failures.append(check)


# ---------------------------------------------------------------------------
# Probe 1 — per-token log-probability.
# ---------------------------------------------------------------------------

def probe_log_prob() -> None:
    fn = load_log_softmax_fn()

    _section("log-prob vs F.log_softmax")
    torch.manual_seed(29)
    logits = torch.randn(3, 5, 10, dtype=torch.float32)
    index = torch.randint(0, 10, (3, 5))
    got = fn(logits, index)
    expected = F.log_softmax(logits, dim=-1).gather(-1, index.unsqueeze(-1)).squeeze(-1)
    diff = (got - expected).abs().max().item()
    _kv("output shape", tuple(got.shape))
    _kv("max abs diff vs F.log_softmax", f"{diff:.2e}",
        flag="? (should be ~0)" if diff > 1e-5 else "")
    # Paired samples make the direction of a sign error obvious.
    for i, (g, e) in enumerate(zip(got.flatten()[:4].tolist(), expected.flatten()[:4].tolist())):
        _kv(f"sample[{i}]", f"got={g:+.4f}  expected={e:+.4f}",
            flag="?" if abs(g - e) > 1e-3 else "")
    if diff > 1e-5:
        _fail("log_prob_vs_reference",
              f"diverges from F.log_softmax by {diff:.2e} — likely a sign flip "
              f"(logsumexp - logit instead of logit - logsumexp), wrong gather axis, "
              f"or off-by-one subtraction")

    _section("log-prob non-positivity")
    torch.manual_seed(123)
    logits = torch.randn(4, 6, 8, dtype=torch.float32)
    index = torch.randint(0, 8, (4, 6))
    out = fn(logits, index)
    mx = out.max().item()
    _kv("max log-prob", f"{mx:+.4f}", flag="? (must be <= 0)" if mx > 1e-6 else "")
    if mx > 1e-6:
        _fail("log_prob_nonpositive",
              f"max log-prob is {mx:+.4f} — log of a probability is always <= 0")

    _section("dominant-token spot check")
    # One logit dominates: its log-prob must be close to 0, not close to the min.
    logits = torch.tensor([[[10.0, 0.0, 0.0]]], dtype=torch.float32)
    lp = fn(logits, torch.tensor([[0]])).item()
    _kv("dominant token log-prob", f"{lp:+.6f}",
        flag="? (should be close to 0)" if not (-1.0 < lp < 0.0) else "")
    if lp > 1e-6:
        _fail("log_prob_dominant", f"dominant-token log-prob is positive ({lp:+.6f})")


# ---------------------------------------------------------------------------
# Probe 2 — group-relative advantage.
# ---------------------------------------------------------------------------

_ADV_EPSILON_RE = re.compile(
    r"/\s*\(\s*std[_a-zA-Z]*\w*\s*\+\s*([0-9.eE+\-]+)\s*\)"
)


def probe_advantage() -> None:
    _section("advantage epsilon (source scan)")
    src_path = locate_advantage_source()
    epsilon = 1e-4  # spec-correct default if no source is found
    if src_path is None:
        print("  skipped scan: advantage-source file not located "
              "(pass a path on argv or edit locate_advantage_source)")
    else:
        with open(src_path) as f:
            source = f.read()
        m = _ADV_EPSILON_RE.search(source)
        if not m:
            print(f"  could not match the `(std... + epsilon)` advantage line in {src_path}")
        else:
            epsilon = float(m.group(1))
            big = epsilon >= 1.0
            _kv("additive epsilon in source", f"{epsilon:g}",
                flag="? (must be << 1, e.g. 1e-4)" if big else "")
            if big:
                _fail("advantage_epsilon",
                      f"additive epsilon is {epsilon:g} — far too large; it dominates "
                      f"the denominator and washes the advantage signal to ~0. Use a "
                      f"small numerical-stability value like 1e-4")

    _section(f"group-relative normalization (epsilon={epsilon:g})")
    # Group 0 has varied rewards (signal); group 1 is constant (no signal).
    rewards = torch.tensor([1.0, 0.0, 0.5, 0.0, 0.5, 0.5, 0.5, 0.5])
    G = 4
    grouped = rewards.view(-1, G)
    mean = grouped.mean(dim=1).repeat_interleave(G, dim=0)
    std = grouped.std(dim=1).repeat_interleave(G, dim=0)
    adv = (rewards - mean) / (std + epsilon)
    _kv("advantages", [f"{x:+.3f}" for x in adv.tolist()])
    g0_max = adv[:G].abs().max().item()
    _kv("group 0 max |A| (varied rewards)", f"{g0_max:.3e}",
        flag="? (vanished despite varied rewards)" if g0_max < 0.1 else "")
    if g0_max < 0.1:
        _fail("advantage_vanishing",
              f"advantages ~0 (max |A|={g0_max:.2e}) on varied rewards — epsilon "
              f"({epsilon:g}) is too large or rewards are degenerate")
    g1_max = adv[G:].abs().max().item()
    _kv("group 1 max |A| (constant rewards)", f"{g1_max:.3e}",
        flag="? (expected ~0)" if g1_max > 1e-3 else "")
    for i in range(2):
        s = adv[i * G:(i + 1) * G].sum().item()
        _kv(f"group {i} sum", f"{s:+.3e}", flag="? (expected ~0, mean-centered)" if abs(s) > 1e-3 else "")


# ---------------------------------------------------------------------------
# Probe 3 — decode / strip round-trip.
# ---------------------------------------------------------------------------

def probe_decode() -> None:
    _section("decode round-trip")
    try:
        tokenizer = load_tokenizer()
    except Exception as e:
        print(f"  skipped: could not load tokenizer ({e})")
        return
    fn = load_decode_fn()

    # (label, text, expect_nonempty)
    cases = [
        ("plain text, no markers", "The answer is <answer>25 + 50</answer>", True),
        ("reasoning + answer", "<think>step by step</think>The answer is <answer>75</answer>", True),
        ("unclosed reasoning", "<think>still thinking and never finished", False),
    ]
    for label, text, expect_nonempty in cases:
        ids = tokenizer(text, return_tensors="pt")["input_ids"]
        out = fn(ids, tokenizer)
        decoded = out[0] if out else "<empty batch>"
        is_empty = len(decoded.strip()) == 0
        flag = ""
        if expect_nonempty and is_empty:
            flag = "? (non-empty completion was blanked — reward fn will see nothing)"
        elif not expect_nonempty and not is_empty:
            flag = "? (unfinished reasoning should blank)"
        _kv(label, f"-> {decoded!r}", flag=flag)
        if expect_nonempty and is_empty:
            _fail("decode_blanks_valid",
                  f"shape {label!r} decoded to empty — a valid completion the reward "
                  f"function must score was stripped; only unclosed reasoning should blank")


# ---------------------------------------------------------------------------
# Runner.
# ---------------------------------------------------------------------------

PROBES = [probe_log_prob, probe_advantage, probe_decode]


def main() -> int:
    for probe in PROBES:
        try:
            probe()
        except Exception as e:
            print(f"\n--- {probe.__name__} ---")
            print(f"  !! probe raised {type(e).__name__}: {e}")
            _hard_failures.append(probe.__name__)

    print()
    if _hard_failures:
        print(f"Unambiguous spec violations in: {', '.join(_hard_failures)}")
        print("Lines marked `?` flag values worth inspecting but are not definitive.")
        return 1
    print("No unambiguous spec violations. Review lines marked `?` before concluding.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _argv_path = sys.argv[1]
        locate_advantage_source = lambda: _argv_path  # noqa: E731
    sys.exit(main())
