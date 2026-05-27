#!/usr/bin/env python3
"""Inspect the GRPO trainer at /app/trl for the high-priority bug sites.

Runs static checks over /app/trl/trl/trainer/grpo_trainer.py (or whatever
file defines GRPOTrainer) and prints findings. Does NOT modify anything.

Usage:
    python scripts/inspect_grpo.py
    python scripts/inspect_grpo.py --trl /path/to/trl/repo

This is a heuristic scan — it pattern-matches for the regressions listed
in references/known-bug-sites.md. A clean report does not prove the code
is correct; a flagged line is a place to read carefully.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PATTERNS = [
    {
        "name": "advantage-reduction-axis",
        "regex": re.compile(
            r"rewards\.(mean|std)\s*\(\s*\)"
        ),
        "hint": (
            "Bare rewards.mean()/std() with no dim — usually means the group "
            "reshape was dropped. Correct form reduces over dim=1 of "
            "rewards.view(-1, num_generations)."
        ),
    },
    {
        "name": "advantage-no-group-view",
        "regex": re.compile(
            r"\(rewards\s*-\s*rewards\.mean\(\)\)\s*/\s*\(rewards\.std\(\)"
        ),
        "hint": (
            "Advantage normalized over the whole batch, not per group. "
            "Restore the per-group view: rewards.view(-1, num_generations)."
        ),
    },
    {
        "name": "missing-eps",
        "regex": re.compile(
            r"/\s*rewards\.view\([^)]*\)\.std\([^)]*\)\s*(?!\s*\+)"
        ),
        "hint": (
            "Division by std without a visible '+ eps'. Check whether the "
            "eps was removed or moved outside the parens."
        ),
    },
    {
        "name": "no_grad-around-policy",
        "regex": re.compile(
            r"with\s+torch\.no_grad\(\):\s*\n[^#\n]*self\.model"
        ),
        "hint": (
            "A torch.no_grad() block contains a call against self.model — "
            "if this is the policy forward, the loss will have no grad_fn."
        ),
    },
    {
        "name": "detach-on-policy-logps",
        "regex": re.compile(r"per_token_logps\.detach\(\)"),
        "hint": (
            "per_token_logps.detach() will break the gradient flow into the "
            "policy. Reference logprobs may be detached; policy must not."
        ),
    },
    {
        "name": "mask-wrong-slice",
        "regex": re.compile(
            r"attention_mask\[\s*:\s*,\s*:\s*-\s*1\s*\]"
        ),
        "hint": (
            "attention_mask[:, :-1] — likely off-by-one. Per-token logprobs "
            "align with input_ids[:, 1:], so the matching mask is "
            "attention_mask[:, 1:]."
        ),
    },
    {
        "name": "loss-sign-suspect",
        "regex": re.compile(
            r"per_token_loss\s*=\s*advantages[^=\n]*\*\s*per_token_logps"
        ),
        "hint": (
            "per_token_loss assigned without a leading '-'. GRPO loss is "
            "-A * logπ; a missing minus inverts the gradient."
        ),
    },
    {
        "name": "view-shape-swapped",
        "regex": re.compile(
            r"rewards\.view\(\s*self\.num_generations\s*,\s*-1\s*\)"
        ),
        "hint": (
            "view(num_generations, -1) swaps the axes — group reduction "
            "will then run over prompts, not over within-group samples."
        ),
    },
]


def find_grpo_trainer(trl_root: Path) -> Path | None:
    """Locate grpo_trainer.py inside the TRL source tree."""
    candidates = list(trl_root.rglob("grpo_trainer.py"))
    if not candidates:
        return None
    # Prefer the canonical trainer path.
    for c in candidates:
        if "trainer" in c.parts:
            return c
    return candidates[0]


def scan_file(path: Path) -> list[dict]:
    """Return a list of {pattern, line_number, line, hint} findings."""
    findings: list[dict] = []
    text = path.read_text()
    lines = text.splitlines()
    for spec in PATTERNS:
        for match in spec["regex"].finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            findings.append({
                "pattern": spec["name"],
                "line_number": line_no,
                "line": line.strip(),
                "hint": spec["hint"],
            })
    return findings


def git_recent_commits(trl_root: Path) -> str:
    """Return `git log --oneline -10` against the trl repo, or an error note."""
    try:
        out = subprocess.run(
            ["git", "-C", str(trl_root), "log", "--oneline", "-10",
             "--", "trl/trainer/grpo_trainer.py", "trl/trainer/grpo_config.py"],
            capture_output=True, text=True, check=False,
        )
        if out.returncode != 0:
            return f"(git log failed: {out.stderr.strip()})"
        return out.stdout.strip() or "(no commits touching GRPO trainer files found)"
    except FileNotFoundError:
        return "(git not available)"


def verify_install_resolves(trl_root: Path) -> str:
    """Check whether `import trl` resolves inside trl_root."""
    try:
        out = subprocess.run(
            [sys.executable, "-c", "import trl, os; print(os.path.dirname(trl.__file__))"],
            capture_output=True, text=True, check=False,
        )
        if out.returncode != 0:
            return f"trl not importable: {out.stderr.strip()}"
        resolved = out.stdout.strip()
        try:
            Path(resolved).resolve().relative_to(trl_root.resolve())
            return f"OK: import trl -> {resolved}"
        except ValueError:
            return (
                f"WARNING: import trl -> {resolved} (not under {trl_root}). "
                "Edits to the source tree will be invisible. Run: "
                f"pip install -e {trl_root} --force-reinstall --no-deps"
            )
    except Exception as exc:
        return f"(install check failed: {exc})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trl", type=Path, default=Path("/app/trl"),
                        help="Path to the TRL source root (default: /app/trl)")
    args = parser.parse_args()

    trl_root = args.trl
    if not trl_root.exists():
        print(f"ERROR: {trl_root} does not exist", file=sys.stderr)
        return 1

    print(f"=== inspect_grpo: scanning {trl_root} ===\n")

    print("--- install check ---")
    print(verify_install_resolves(trl_root))
    print()

    print("--- recent commits touching GRPO files ---")
    print(git_recent_commits(trl_root))
    print()

    trainer = find_grpo_trainer(trl_root)
    if trainer is None:
        print(f"ERROR: no grpo_trainer.py found under {trl_root}",
              file=sys.stderr)
        return 1
    print(f"--- scanning {trainer} ---")
    findings = scan_file(trainer)
    if not findings:
        print("(no pattern matches — the bug is likely subtle; instrument "
              "via the full-audit mode in SKILL.md)")
    else:
        for f in findings:
            print(f"\n[{f['pattern']}] line {f['line_number']}: {f['line']}")
            print(f"   hint: {f['hint']}")

    print("\n=== inspect_grpo done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
