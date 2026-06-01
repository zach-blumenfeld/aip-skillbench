"""Paper figure: combined trial-outcome matrix across the four eval runs.

Tasks (rows) × modes (human-curated vs aip-from-curated). Each cell shows the
5 per-trial outcomes as sorted markers (pass → fail → timeout), followed by the
per-task mean reward and mean wall-clock over those 5 trials. Tasks are grouped
by the AIP spec version their packs were built under. All "error" outcomes in
these runs are timeouts (hard wall-clock cap or idle/stall), scored as reward 0,
so the means are computed over all five trials (consistent with the paper's
aggregate reward and wall-clock).

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

PASS_C, FAIL_C, TO_EDGE = "#2e8b40", "#d1495b", "#9aa0a6"
WIN_C, INK = "#1f6f2c", "#2b2f36"
ORDER = {"pass": 0, "fail": 1, "timeout": 2}
STYLE = {
    "pass": dict(marker="o", s=95, facecolor=PASS_C, edgecolor=PASS_C, linewidths=1.2),
    "fail": dict(marker="X", s=95, facecolor=FAIL_C, edgecolor=FAIL_C, linewidths=1.2),
    "timeout": dict(marker="o", s=80, facecolor="white", edgecolor=TO_EDGE, linewidths=1.4),
}

# x-geometry: 5 markers, then a mean-reward column and a mean-wall column, per block.
HUMAN_X = [0, 1, 2, 3, 4]
HUMAN_R_X, HUMAN_W_X = 5.7, 7.1            # right-aligned numeric columns
SEP_X = 7.7
AIP_X = [8.4, 9.4, 10.4, 11.4, 12.4]
AIP_R_X, AIP_W_X = 14.1, 15.5
XMIN, XMAX = -0.7, 15.7
BLOCK_CENTERS = [3.2, 11.6]                # mode header centred over each block
NUMCOLS = [(HUMAN_R_X, HUMAN_W_X), (AIP_R_X, AIP_W_X)]


def spec_version(run_dir: Path) -> str:
    return "v0.3a2" if "v0_3a2" in run_dir.name else "v0.3a3"


def load(run_dirs):
    """Return (groups, results, rewards, walls).
    results: {(task, mode): [statuses sorted pass<fail<timeout]}
    rewards/walls: {(task, mode): [floats]} over the trials."""
    by_version: dict[str, list[str]] = {}
    results: dict[tuple[str, str], list[str]] = {}
    rewards: dict[tuple[str, str], list[float]] = {}
    walls: dict[tuple[str, str], list[float]] = {}
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
            key = (r["task"], mode)
            status = "timeout" if r["status"] == "error" else r["status"]
            results.setdefault(key, []).append(status)
            if r.get("reward") is not None:
                rewards.setdefault(key, []).append(r["reward"])
            if r.get("wall_clock") is not None:
                walls.setdefault(key, []).append(r["wall_clock"])
    for k in results:
        results[k].sort(key=lambda s: ORDER[s])
    groups = [(v, sorted(by_version[v])) for v in ["v0.3a3", "v0.3a2"] if v in by_version]
    return groups, results, rewards, walls


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def plot(groups, results, rewards, walls, out: Path, title: str | None):
    GROUP_LABEL = {
        "v0.3a3": "AIP spec v0.3a3 — stratified cohort",
        "v0.3a2": "AIP spec v0.3a2 — supporting set",
    }
    layout = []  # (kind, payload, y)
    y = 0.0
    for gi, (ver, tasks) in enumerate(groups):
        if gi > 0:
            y += 0.6
        layout.append(("header", (ver, len(tasks)), y))
        y += 1.0
        for t in tasks:
            layout.append(("task", t, y))
            y += 1.0
    total_h = y

    fig_h = 1.7 + 0.30 * total_h
    fig, ax = plt.subplots(figsize=(11.4, fig_h))

    task_rows = [(p, ry) for kind, p, ry in layout if kind == "task"]
    header_rows = [(p, ry) for kind, p, ry in layout if kind == "header"]

    for i, (_, ry) in enumerate(task_rows):
        if i % 2 == 0:
            ax.axhspan(ry - 0.5, ry + 0.5, color="#f4f5f7", zorder=0)

    for (ver, ntask), ry in header_rows:
        ax.axhspan(ry - 0.5, ry + 0.5, color="#e7ebf0", zorder=0)
        ax.text(-0.55, ry, f"{GROUP_LABEL[ver]}  ({ntask} tasks)",
                ha="left", va="center", fontsize=9.5, fontweight="bold", color=INK)

    ax.axvline(SEP_X, color="#d0d4da", linewidth=0.8, zorder=1)

    for task, ry in task_rows:
        mode_r = {}  # mode -> mean reward, to bold the strictly-higher one
        for mode, _ in MODES:
            mode_r[mode] = mean(rewards.get((task, mode), []))
        # Only one mode wins highlighting, and only on a strict difference —
        # ties (equal mean reward) get no highlight.
        present = [(m, v) for m, v in mode_r.items() if v is not None]
        winner_mode = None
        if len(present) == 2:
            (m0, v0), (m1, v1) = present
            if abs(v0 - v1) > 1e-9:
                winner_mode = m0 if v0 > v1 else m1

        for (mode, _), xs, (rx, wx) in zip(MODES, (HUMAN_X, AIP_X), NUMCOLS):
            for x, st in zip(xs, results.get((task, mode), [])):
                ax.scatter(x, ry, zorder=3, **STYLE[st])
            mr = mode_r[mode]
            mw = mean(walls.get((task, mode), []))
            if mr is not None:
                is_best = mode == winner_mode
                ax.text(rx, ry, f"{mr:.2f}", ha="right", va="center", fontsize=9.0,
                        fontfamily="monospace", color=WIN_C if is_best else INK,
                        fontweight="bold" if is_best else "normal", zorder=3)
            if mw is not None:
                ax.text(wx, ry, f"{mw:.0f}", ha="right", va="center", fontsize=9.0,
                        fontfamily="monospace", color="#5b616b", zorder=3)

    ax.set_yticks([ry for _, ry in task_rows])
    ax.set_yticklabels([t for t, _ in task_rows], fontsize=8, fontfamily="monospace")
    ax.tick_params(axis="y", length=0)

    # headers: mode name over each block, plus small numeric-column labels
    head_y, sub_y = -1.7, -0.85
    for (_, label), cx in zip(MODES, BLOCK_CENTERS):
        ax.text(cx, head_y, label, ha="center", va="bottom",
                fontsize=10, fontweight="bold", color=INK)
    for rx, wx in NUMCOLS:
        ax.text(rx, sub_y, "mean R", ha="right", va="center", fontsize=8.5,
                style="italic", color="#5b616b")
        ax.text(wx, sub_y, "wall (s)", ha="right", va="center", fontsize=8.5,
                style="italic", color="#5b616b")

    ax.set_xlim(XMIN, XMAX)
    ax.set_ylim(total_h - 0.5, head_y - 0.4)
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    handles = [
        Line2D([0], [0], linestyle="none", marker="o", markersize=9,
               markerfacecolor=PASS_C, markeredgecolor=PASS_C, label="pass (reward = 1)"),
        Line2D([0], [0], linestyle="none", marker="X", markersize=9,
               markerfacecolor=FAIL_C, markeredgecolor=FAIL_C, label="fail (reward < 1)"),
        Line2D([0], [0], linestyle="none", marker="o", markersize=9,
               markerfacecolor="white", markeredgecolor=TO_EDGE, markeredgewidth=1.4,
               label="timeout (wall-clock / idle)"),
        Line2D([0], [0], linestyle="none", marker=r"$\mathbf{0.80}$", markersize=14,
               color=WIN_C, label="higher mean reward of the two formats"),
    ]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0),
              ncol=4, frameon=False, fontsize=9, handletextpad=0.4, columnspacing=1.4)

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

groups, results, rewards, walls = load(args.run_dirs)
plot(groups, results, rewards, walls, args.out, args.title)
