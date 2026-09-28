#!/usr/bin/env python3
"""Upload a run-matrix campaign to HuggingFace, gated on a credential scan.

Agent trajectories (`acp_trajectory.jsonl`) ARE included by default — they are research
data. Safety comes from the scan, not from withholding them: every file that would be
uploaded is scanned for credential patterns, and on any hit the upload is refused and a
per-finding report is written for manual review.

    uv run python scripts/hf_upload.py --campaign eval-1-haiku --dry-run
    uv run python scripts/hf_upload.py --campaign eval-1-haiku
    uv run python scripts/hf_upload.py --campaign eval-1-haiku --exclude-trajectories

Exit codes: 0 clean, 1 findings need review, 2 bad usage.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.utils import filter_repo_objects

REPO_ROOT = Path(__file__).resolve().parent.parent

# Excluded by default: bulky and recreatable. Agent trajectories are NOT here — they are
# research data and ship by default, protected by the scan rather than by omission.
DEFAULT_IGNORE = [
    "**/compressed_video.mp4",   # ~600 MB of recreatable video-silence-remover output
    "**/install-stdout.txt",     # noisy, recreatable
    "**/.git/**",
    "**/.DS_Store",
]
TRAJECTORY_PATTERN = "**/acp_trajectory.jsonl"

# Layer 2 — credential patterns. Tuned against the full corpus: catches the 2026-09-02
# civ6-adjacency-optimizer leak, zero false positives across 5 clean campaigns.
SECRET_PATTERNS = {
    "anthropic":       r"sk-ant-[A-Za-z0-9_-]{20,}",
    "openai-project":  r"sk-proj-[A-Za-z0-9_-]{20,}",
    "openai-legacy":   r"sk-[A-Za-z0-9]{32,}",
    "huggingface":     r"hf_[A-Za-z0-9]{30,}",
    "github":          r"gh[pousr]_[A-Za-z0-9]{30,}",
    "aws":             r"A(?:KIA|SIA)[0-9A-Z]{16}",
    "gcp":             r"AIza[0-9A-Za-z_-]{35}",
    "slack":           r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "nams":            r"nams_[A-Za-z0-9_-]{20,}",
    # Generic assignment. Deliberately API_KEY (not _KEY) so GPG_KEY, a public signing
    # fingerprint that appears in every env dump, does not trip the gate.
    "generic-assign":  r"[A-Z_]*(?:API_KEY|AUTH_TOKEN|ACCESS_TOKEN|CLIENT_SECRET|PASSWORD)=[^\"\\\s]{12,}",
    "db-uri-creds":    r"(?:neo4j|bolt|postgres|mysql|mongodb)(?:\+s{0,4})?://[^\s\"]*:[^\s\"@]+@",
}
SECRET_RE = re.compile("|".join(f"(?P<{k.replace('-', '_')}>{v})" for k, v in SECRET_PATTERNS.items()).encode())

SCANNABLE = {".jsonl", ".json", ".txt", ".md", ".csv", ".log", ".py", ".sh", ".yaml", ".yml", ".env", ".cfg", ".ini", ""}


def files_to_upload(folder: Path, ignore: list[str]) -> list[Path]:
    """Exactly the set huggingface_hub would upload, via its own matcher."""
    rel = [str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()]
    kept = filter_repo_objects(rel, ignore_patterns=ignore)
    return [folder / r for r in kept]


MAX_PER_FILE = 25


def mask(raw: bytes) -> str:
    """Show enough to identify the credential type, never enough to use it."""
    t = raw.decode("utf-8", "replace")
    if "=" in t and not t.startswith(("sk-", "hf_", "gh", "xox", "AIza", "AKIA", "ASIA", "nams_")):
        name, _, val = t.partition("=")
        return f"{name}={val[:4]}...[{len(val)} chars redacted]"
    return f"{t[:12]}...[{len(t)} chars redacted]"


def scan(paths: list[Path]) -> list[dict]:
    """Every finding, with line number and masked context, for manual review.

    The whole line is sanitized before any context is extracted, so a finding's context
    can never expose a neighbouring secret in raw form.
    """
    findings: list[dict] = []
    for p in paths:
        if p.suffix.lower() not in SCANNABLE:
            continue
        try:
            blob = p.read_bytes()
        except OSError:
            continue
        if not SECRET_RE.search(blob):
            continue
        n = 0
        for lineno, line in enumerate(blob.split(b"\n"), 1):
            matches = list(SECRET_RE.finditer(line))
            if not matches:
                continue
            # Rebuild the line with EVERY secret replaced, tracking where each landed.
            out, pos, spots = bytearray(), 0, []
            for mm in matches:
                out += line[pos:mm.start()]
                start = len(out)
                out += ("<<<" + mask(mm.group(0)) + ">>>").encode()
                spots.append((start, len(out)))
                pos = mm.end()
            out += line[pos:]
            safe = bytes(out)
            for mm, (lo_i, hi_i) in zip(matches, spots):
                ctx = safe[max(0, lo_i - 60):min(len(safe), hi_i + 40)].decode("utf-8", "replace")
                findings.append({
                    "path": p, "line": lineno,
                    "kind": (mm.lastgroup or "unknown").replace("_", "-"),
                    "masked": mask(mm.group(0)),
                    "context": " ".join(ctx.split())[:220],
                })
                n += 1
                if n >= MAX_PER_FILE:
                    break
            if n >= MAX_PER_FILE:
                findings.append({"path": p, "line": 0, "kind": "truncated",
                                 "masked": f"(more than {MAX_PER_FILE} findings in this file)",
                                 "context": ""})
                break
    return findings


def write_report(findings: list[dict], campaign: str) -> Path:
    out_dir = REPO_ROOT / ".secret-scan"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{campaign}.txt"
    by_file: dict[Path, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["path"], []).append(f)
    lines = [
        f"SECRET SCAN REPORT - campaign: {campaign}",
        f"{len(findings)} finding(s) in {len(by_file)} file(s)",
        "",
        "Values are masked. This report is safe to read and share internally.",
        "",
    ]
    for path, items in sorted(by_file.items()):
        lines.append(f"--- {path.relative_to(REPO_ROOT)}")
        for it in items:
            if it["kind"] == "truncated":
                lines.append(f"      {it['masked']}")
                continue
            lines.append(f"  L{it['line']}  [{it['kind']}]  {it['masked']}")
            if it["context"]:
                lines.append(f"        ...{it['context']}...")
        lines.append("")
    out.write_text("\n".join(lines))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", required=True, help="directory name under runs/")
    ap.add_argument("--org", default="neo4j")
    ap.add_argument("--dataset", default=None, help="repo name (default: experiment-aip-skillbench-<campaign>)")
    ap.add_argument("--private", action="store_true", default=True)
    ap.add_argument("--public", dest="private", action="store_false")
    ap.add_argument("--dry-run", action="store_true", help="scan and report; upload nothing")
    ap.add_argument("--exclude-trajectories", action="store_true",
                    help="drop acp_trajectory.jsonl instead of uploading it. Trajectories "
                         "ship by default; use this only when you deliberately want them out.")
    args = ap.parse_args()

    folder = REPO_ROOT / "runs" / args.campaign
    if not folder.is_dir():
        print(f"error: {folder} not found", file=sys.stderr)
        return 2

    ignore = list(DEFAULT_IGNORE)
    if args.exclude_trajectories:
        ignore.append(TRAJECTORY_PATTERN)

    all_files = [p for p in folder.rglob("*") if p.is_file()]
    upload = files_to_upload(folder, ignore)
    print(f"campaign : {args.campaign}")
    print(f"files    : {len(all_files)} on disk -> {len(upload)} after exclusion "
          f"({len(all_files) - len(upload)} dropped)")
    n_traj = sum(1 for f in upload if f.name == "acp_trajectory.jsonl")
    print(f"trajectories: {'excluded' if args.exclude_trajectories else f'{n_traj} included'}")

    print(f"scanning {len(upload)} files for credentials...")
    findings = scan(upload)
    if findings:
        n_files = len({f["path"] for f in findings})
        report = write_report(findings, args.campaign)
        print()
        print("=" * 78)
        print("  UPLOAD BLOCKED - MANUAL REVIEW REQUIRED")
        print("=" * 78)
        print(f"  {len(findings)} credential finding(s) across {n_files} file(s).")
        print(f"  Nothing was uploaded. Full report: {report.relative_to(REPO_ROOT)}")
        print()
        by_file: dict = {}
        for f in findings:
            by_file.setdefault(f["path"], []).append(f)
        for path, items in sorted(by_file.items())[:10]:
            print(f"  {path.relative_to(REPO_ROOT)}")
            for it in items[:3]:
                loc = f"L{it['line']}" if it["line"] else "  "
                print(f"      {loc}  [{it['kind']}]  {it['masked']}")
            if len(items) > 3:
                print(f"      ... {len(items) - 3} more in this file")
        if len(by_file) > 10:
            print(f"  ... and {len(by_file) - 10} more file(s) - see the report")
        print()
        print("  Review each finding, then choose:")
        print("    1. False positive      -> tighten SECRET_PATTERNS in this script")
        print("    2. Real credential     -> REVOKE IT FIRST, then redact in place")
        print("                              (see scratch/redact-leaked-key.md) and re-run")
        print("    3. Confined to traces  -> re-run with --exclude-trajectories")
        print("=" * 78)
        return 1
    print("SECRET SCAN PASSED - no credential patterns found")

    if args.dry_run:
        print("\n--dry-run: nothing uploaded")
        return 0

    dataset = args.dataset or f"experiment-aip-skillbench-{args.campaign}"
    repo_id = f"{args.org}/{dataset}"
    api = HfApi()
    api.create_repo(repo_id, repo_type="dataset", private=args.private, exist_ok=True)

    api.upload_folder(repo_id=repo_id, repo_type="dataset", folder_path=str(folder),
                      ignore_patterns=ignore,
                      commit_message=f"Upload {args.campaign}")

    for src, dst in ((REPO_ROOT / "reports" / f"{args.campaign}.md", "README.md"),
                     (REPO_ROOT / "README.md", "REPO-README.md")):
        if src.exists():
            api.upload_file(path_or_fileobj=str(src), path_in_repo=dst,
                            repo_id=repo_id, repo_type="dataset",
                            commit_message=f"Add {dst}")

    print(f"\nuploaded -> https://huggingface.co/datasets/{repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
