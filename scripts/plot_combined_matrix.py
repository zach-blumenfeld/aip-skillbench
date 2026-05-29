"""Paper figure: combined trial-outcome matrix across the four eval runs.

Tasks (rows) × modes (human-curated vs aip-from-curated), each cell showing the
5 per-trial outcomes as sorted markers (pass → fail → timeout). Tasks are
grouped by the AIP spec version their packs were built under. All "error"
outcomes in these runs are timeouts (hard wall-clock cap or idle/stall), so we
label them "timeout".

Usage:
    uv run python scripts/plot_combined_matrix.py \
        runs/eval-cohort-a-sonnet-aipv0_3a3 \
        runs/eval-cohort-b-sonnet-aipv0_3a3 \
        runs/eval-cohort-c-sonnet-aipv0_3a3 \
        runs/eval-3med-sonnet-v0_3a2 \
        --out figures/combined-matrix
Writes <out>.pdf and <out>.png.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

MODES = [("human-curated", "human-curated"), ("aip-from-curated", "aip-from-curated")]
TRIALS = 5

# outcome -> (sort order, color, marker style kwargs)
PASS_C, FAIL_C, TO_EDGE = "#2e8b40", "#d1495b", "#9aa0a6"
ORDER = {"pass": 0, "fail": 1, "timeout": 2}
STYLE = {
    "pass": dict(marker="o", s=95, facecolor=PASS_C, edgecolor=PASS_C, linewidths=1.2),
    "fail": dict(marker="X", s=95, facecolor=FAIL_C, edgecolor=FAIL_C, linewidths=1.2),
    "timeout": dict(marker="o", s=80, facecolor="white", edgecolor=TO_EDGE, linewidths=1.4),
}

# marker x-positions for each mode block, plus the centred header position
HUMAN_X = [0, 1, 2, 3, 4]
AIP_X = [6.4, 7.4, 8.4, 9.4, 10.4]
BLOCK_CENTERS = [2.0, 8.4]
SEP_X = 5.2


def spec_version(run_dir: Path) -> str:
    return "v0.3a2" if "v0_3a2" in run_dir.name else "v0.3a3"


def load(run_dirs):
    """Return (groups, results). groups: [(version, [tasks...])] in arg order.
    results: {(task, mode): [statuses sorted pass<fail<timeout]}."""
    by_version: dict[str, list[str]] = {}
    order: list[str] = []
    results: dict[tuple[str, str], list[str]] = {}
    for run in run_dirs:
        ver = spec_version(run)
        camp = json.loads((run / "campaign.json").read_text())
        for t in camp["tasks"]:
            by_version.setdefault(ver, [])
            if t not in by_version[ver]:
                by_version[ver].append(t)
        for line in (run / "summary.jsonl").read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            mode = r["mode"]
            if mode not in {m for m, _ in MODES}:
                continue
            status = "timeout" if r["status"] == "error" else r["status"]
            results.setdefault((r["task"], mode), []).append(status)
    for k in results:
        results[k].sort(key=lambda s: ORDER[s])
    # groups ordered v0.3a3 first (the primary cohort), then v0.3a2;
    # tasks sorted alphabetically within each group for readability
    groups = [(v, sorted(by_version[v])) for v in ["v0.3a3", "v0.3a2"] if v in by_version]
    return groups, results


def plot(groups, results, out: Path, title: str | None):
    GROUP_LABEL = {
        "v0.3a3": "AIP spec v0.3a3 — stratified cohort",
        "v0.3a2": "AIP spec v0.3a2 — supporting set",
    }
    # Lay out rows top→down. Headers get their own row; tasks get one each.
    layout = []  # (kind, payload, y)
    y = 0.0
    for gi, (ver, tasks) in enumerate(groups):
        if gi > 0:
            y += 0.6  # gap between groups
        layout.append(("header", (ver, len(tasks)), y))
        y += 1.0
        for t in tasks:
            layout.append(("task", t, y))
            y += 1.0
    total_h = y

    fig_h = 1.6 + 0.30 * total_h
    fig, ax = plt.subplots(figsize=(8.4, fig_h))

    task_rows = [(p, ry) for kind, p, ry in layout if kind == "task"]
    header_rows = [(p, ry) for kind, p, ry in layout if kind == "header"]

    # subtle alternating row shading for tasks
    for i, (_, ry) in enumerate(task_rows):
        if i % 2 == 0:
            ax.axhspan(ry - 0.5, ry + 0.5, color="#f4f5f7", zorder=0)

    # group header bands + labels
    for (ver, ntask), ry in header_rows:
        ax.axhspan(ry - 0.5, ry + 0.5, color="#e7ebf0", zorder=0)
        ax.text(-0.55, ry, f"{GROUP_LABEL[ver]}  ({ntask} tasks)",
                ha="left", va="center", fontsize=9.5, fontweight="bold",
                color="#2b2f36")

    # vertical separator between the two mode blocks
    ax.axvline(SEP_X, color="#d0d4da", linewidth=0.8, zorder=1)

    # markers
    for task, ry in task_rows:
        for (mode, _), xs in zip(MODES, (HUMAN_X, AIP_X)):
            statuses = results.get((task, mode), [])
            for x, st in zip(xs, statuses):
                ax.scatter(x, ry, zorder=3, **STYLE[st])

    # task labels (left)
    ax.set_yticks([ry for _, ry in task_rows])
    ax.set_yticklabels([t for t, _ in task_rows], fontsize=8, fontfamily="monospace")
    ax.tick_params(axis="y", length=0)

    # column headers above the top row
    top_y = -1.1
    for (_, label), cx in zip(MODES, BLOCK_CENTERS):
        ax.text(cx, top_y, label, ha="center", va="bottom",
                fontsize=10, fontweight="bold", color="#2b2f36")

    ax.set_xlim(-0.7, 11.1)
    ax.set_ylim(total_h - 0.5, top_y - 0.4)  # inverted: row 0 at top
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # legend / marker key
    handles = [
        Line2D([0], [0], linestyle="none", marker="o", markersize=9,
               markerfacecolor=PASS_C, markeredgecolor=PASS_C, label="pass (reward = 1)"),
        Line2D([0], [0], linestyle="none", marker="X", markersize=9,
               markerfacecolor=FAIL_C, markeredgecolor=FAIL_C, label="fail (reward < 1)"),
        Line2D([0], [0], linestyle="none", marker="o", markersize=9,
               markerfacecolor="white", markeredgecolor=TO_EDGE, markeredgewidth=1.4,
               label="timeout (wall-clock / idle)"),
    ]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0),
              ncol=3, frameon=False, fontsize=9, handletextpad=0.4,
              columnspacing=1.4)

    if title:
        fig.suptitle(title, fontsize=11, y=0.998)

    fig.tight_layout(rect=(0, 0, 1, 0.985))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(f"{out}.pdf", bbox_inches="tight")
    fig.savefig(f"{out}.png", dpi=200, bbox_inches="tight")
    print(f"wrote {out}.pdf and {out}.png  ({len(task_rows)} tasks)")


parser = argparse.ArgumentParser()
parser.add_argument("run_dirs", nargs="+", type=Path)
parser.add_argument("--out", type=Path, default=Path("figures/combined-matrix"))
parser.add_argument("--title", default=None)
args = parser.parse_args()

groups, results = load(args.run_dirs)
plot(groups, results, args.out, args.title)
