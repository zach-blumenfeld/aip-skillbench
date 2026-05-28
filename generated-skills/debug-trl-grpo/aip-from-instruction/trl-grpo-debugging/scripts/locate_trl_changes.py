#!/usr/bin/env python3
"""Triage a TRL source tree for a planted GRPO bug.

Locates the GRPO trainer + helpers, surfaces any version-control diff (the fastest
path to a planted edit), and greps the key GRPO computation sites so the agent reads
the right ~50 lines instead of the whole library.

Usage:
    python3 locate_trl_changes.py [--trl-path /app/trl] [--app-root /app]

Output contract:
    stdout : human-readable triage report.
    stderr : JSON Lines, one record per finding {"kind","detail",...}. Stream-parse
             to drive the next step.
    exit   : 0 always (this is a locator, not a validator). Read the report.

Stdlib only; runs under `uv run` or plain `python3`.
"""
import argparse
import json
import os
import subprocess
import sys

# GRPO computation sites worth reading. (label, regex) — regex is grep -E syntax.
SITE_PATTERNS = [
    ("gradient-connectivity (no_grad/detach)", r"no_grad|inference_mode|\.detach\(|requires_grad"),
    ("advantage (center/scale)", r"advantage|mean_grouped|std_grouped|scale_rewards"),
    ("group broadcast (repeat vs interleave)", r"repeat_interleave|\.repeat\(|\.view\(|num_generations"),
    ("ratio / clip", r"torch\.exp|coef_1|coef_2|clamp|epsilon"),
    ("loss sign / min", r"torch\.min|per_token_loss|-\s*torch\.min"),
    ("completion mask", r"completion_mask|attention_mask"),
    ("logp / token shift", r"selective_log_softmax|logits\[|input_ids\[|gather|log_softmax"),
    ("KL / beta", r"per_token_kl|self\.beta|ref_per_token"),
]

# Files the task forbids editing — flag if the caller points at them.
OFF_LIMITS = ("train_grpo.py", "reward_fn.py")


def emit(kind, detail, **extra):
    rec = {"kind": kind, "detail": detail}
    rec.update(extra)
    print(json.dumps(rec), file=sys.stderr)


def run(cmd, cwd=None):
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return out.returncode, out.stdout, out.stderr
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)


def find_trainer_files(trl_path):
    """Return GRPO-relevant python files under the trl tree."""
    hits = []
    for root, _dirs, files in os.walk(trl_path):
        if ".git" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            low = f.lower()
            full = os.path.join(root, f)
            if "grpo" in low:
                hits.append((full, "grpo"))
            elif f in ("utils.py", "grpo_config.py") or "reward" in low:
                hits.append((full, "helper"))
    # GRPO trainer first
    hits.sort(key=lambda t: (t[1] != "grpo", t[0]))
    return hits


def git_intel(root):
    """If root (or an ancestor) is a git repo, return diff/status/log intel."""
    code, top, _ = run(["git", "rev-parse", "--show-toplevel"], cwd=root)
    if code != 0:
        return None
    top = top.strip()
    _, status, _ = run(["git", "status", "--porcelain"], cwd=top)
    _, diff, _ = run(["git", "diff", "--stat"], cwd=top)
    _, log, _ = run(["git", "log", "--oneline", "-8"], cwd=top)
    _, full_diff, _ = run(["git", "diff"], cwd=top)
    return {"top": top, "status": status, "diff_stat": diff, "log": log, "full_diff": full_diff}


def grep_sites(path):
    """Return {label: [(lineno, text), ...]} for each GRPO site pattern in path."""
    try:
        with open(path, "r", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return {}
    import re

    out = {}
    for label, pat in SITE_PATTERNS:
        rx = re.compile(pat)
        matched = [(i + 1, ln.rstrip("\n")) for i, ln in enumerate(lines) if rx.search(ln)]
        if matched:
            out[label] = matched
    return out


def main():
    ap = argparse.ArgumentParser(description="Triage a TRL tree for a planted GRPO bug.")
    ap.add_argument("--trl-path", default="/app/trl", help="Path to the trl package/source tree.")
    ap.add_argument("--app-root", default="/app", help="App root (for off-limits file reminder).")
    ap.add_argument("--max-lines", type=int, default=4, help="Max grep hits to print per site per file.")
    args = ap.parse_args()

    print("=" * 72)
    print("TRL GRPO bug triage")
    print("=" * 72)

    if not os.path.exists(args.trl_path):
        print(f"!! trl path not found: {args.trl_path}  (pass --trl-path)")
        emit("error", "trl-path-missing", path=args.trl_path)
        return 0

    # 1) Off-limits reminder.
    print("\n[scope] These files MUST NOT be edited — the fix goes in the trl source only:")
    for f in OFF_LIMITS:
        p = os.path.join(args.app_root, f)
        mark = "exists" if os.path.exists(p) else "not found"
        print(f"    - {p}  ({mark})")
        emit("off_limits", f, path=p, exists=os.path.exists(p))

    # 2) Version control — the prime suspect for a planted edit.
    print("\n[git] checking whether the trl tree is version-controlled...")
    gi = git_intel(args.trl_path)
    if gi:
        print(f"    repo root: {gi['top']}")
        if gi["status"].strip():
            print("    *** UNCOMMITTED CHANGES present — inspect these FIRST: ***")
            print("    " + gi["status"].replace("\n", "\n    ").rstrip())
            emit("git_dirty", "uncommitted-changes", files=gi["status"].strip().splitlines())
        else:
            print("    working tree clean (planted bug may be committed — check recent log/diff)")
        if gi["diff_stat"].strip():
            print("    diff --stat:")
            print("    " + gi["diff_stat"].replace("\n", "\n    ").rstrip())
        print("    recent commits:")
        print("    " + gi["log"].replace("\n", "\n    ").rstrip())
        if gi["full_diff"].strip():
            emit("git_diff", "non-empty", chars=len(gi["full_diff"]))
            print("\n    >>> A non-empty `git diff` is the highest-signal lead. Run:")
            print(f"        git -C {gi['top']} diff")
    else:
        print("    not a git repo (or git unavailable) — fall back to code-vs-reference diff.")
        emit("git_absent", "no-vcs", path=args.trl_path)

    # 3) Locate GRPO files + grep computation sites.
    files = find_trainer_files(args.trl_path)
    if not files:
        print("\n[files] no GRPO/helper python files found under trl path.")
        emit("error", "no-grpo-files", path=args.trl_path)
        return 0
    print(f"\n[files] GRPO-relevant source ({len(files)} found):")
    for full, kind in files:
        print(f"    - {full}  [{kind}]")
        emit("grpo_file", full, file_kind=kind)

    print("\n[sites] key GRPO computation sites (read these against references/grpo-algorithm.md):")
    for full, kind in files:
        sites = grep_sites(full)
        if not sites:
            continue
        print(f"\n  {full}")
        for label, matched in sites.items():
            shown = matched[: args.max_lines]
            print(f"    · {label}:")
            for lineno, text in shown:
                print(f"        {lineno}: {text.strip()[:110]}")
            if len(matched) > len(shown):
                print(f"        ... (+{len(matched) - len(shown)} more)")
            emit("site", label, file=full, line_count=len(matched))

    print("\n" + "=" * 72)
    print("Next: if `git diff` was non-empty, read it — that is the plant. Otherwise compare")
    print("each site above against references/grpo-algorithm.md, then confirm with a runtime")
    print("metric via instrumentation + scripts/grpo_invariants.py.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
