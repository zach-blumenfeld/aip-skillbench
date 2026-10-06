#!/usr/bin/env python3
"""Build the full dice-game analysis from the simulation workbook.

Reads one JSON object on stdin ({"currentState": {"data_file": "<path>", ...}, ...})
and writes one JSON object on stdout containing per-turn category scores,
best turn score, best game score (two turns, distinct categories), and summary
statistics covering the questions in the Round 1 Section 3 case pack.
"""

import json
import os
import statistics
import sys
from collections import Counter


CATEGORY_ORDER = [
    "high_and_often",
    "summation",
    "highs_and_lows",
    "only_two_numbers",
    "all_the_numbers",
    "ordered_subset_of_four",
]
CATEGORY_LABEL = {
    "high_and_often": "High and Often",
    "summation": "Summation",
    "highs_and_lows": "Highs and Lows",
    "only_two_numbers": "Only two numbers",
    "all_the_numbers": "All the numbers",
    "ordered_subset_of_four": "Ordered subset of four",
}


def score_high_and_often(rolls):
    hi = max(rolls)
    return hi * rolls.count(hi)


def score_summation(rolls):
    return sum(rolls)


def score_highs_and_lows(rolls):
    hi, lo = max(rolls), min(rolls)
    return hi * lo * (hi - lo)


def score_only_two_numbers(rolls):
    return 30 if len(set(rolls)) <= 2 else 0


def score_all_the_numbers(rolls):
    return 40 if set(rolls) == {1, 2, 3, 4, 5, 6} else 0


def score_ordered_subset_of_four(rolls):
    # Any run of 4 consecutive numbers in rolled order, increasing by 1 or
    # decreasing by 1. e.g. 1-2-3-4 or 5-4-3-2 anywhere in positions 1..3.
    for start in range(len(rolls) - 3):
        window = rolls[start:start + 4]
        diffs = [window[i + 1] - window[i] for i in range(3)]
        if diffs == [1, 1, 1] or diffs == [-1, -1, -1]:
            return 50
    return 0


SCORERS = {
    "high_and_often": score_high_and_often,
    "summation": score_summation,
    "highs_and_lows": score_highs_and_lows,
    "only_two_numbers": score_only_two_numbers,
    "all_the_numbers": score_all_the_numbers,
    "ordered_subset_of_four": score_ordered_subset_of_four,
}


def load_turns(path):
    """Return list of dicts: {turn, game, rolls:[6 ints]}, in sheet order."""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    # Prefer a sheet literally named 'Data', else first sheet whose header row
    # matches the expected columns.
    sheet = None
    if "Data" in wb.sheetnames:
        sheet = wb["Data"]
    else:
        sheet = wb[wb.sheetnames[0]]

    header_row = None
    turn_col = game_col = None
    roll_cols = []
    for row_idx, row in enumerate(
        sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 50), values_only=True),
        start=1,
    ):
        norm = [str(v).strip().lower() if v is not None else "" for v in row]
        if "turn number" in norm and "game number" in norm:
            header_row = row_idx
            for col_idx, v in enumerate(norm, start=1):
                if v == "turn number":
                    turn_col = col_idx
                elif v == "game number":
                    game_col = col_idx
                elif v.startswith("roll "):
                    roll_cols.append((v, col_idx))
            break
    if header_row is None:
        raise RuntimeError("Could not find 'Turn number'/'Game number' header row in workbook")
    roll_cols.sort(key=lambda x: int(x[0].split()[1]))
    roll_cols = [c for _, c in roll_cols]
    if len(roll_cols) != 6 or turn_col is None or game_col is None:
        raise RuntimeError(f"Unexpected header layout: turn={turn_col} game={game_col} rolls={roll_cols}")

    turns = []
    for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
        if turn_col > len(row) or game_col > len(row):
            continue
        turn_cell = row[turn_col - 1]
        game_cell = row[game_col - 1]
        if turn_cell is None or game_cell is None:
            continue
        try:
            turn = int(turn_cell)
            game = int(game_cell)
            rolls = [int(row[c - 1]) for c in roll_cols]
        except (TypeError, ValueError):
            continue
        turns.append({"turn": turn, "game": game, "rolls": rolls})
    return turns


def score_turn(rolls):
    return {cat: SCORERS[cat](rolls) for cat in CATEGORY_ORDER}


def best_game_score(scores_a, scores_b):
    """Return (best_total, cat_a, cat_b) across all distinct-category pairs."""
    best = -1
    best_pair = (None, None)
    for ca in CATEGORY_ORDER:
        for cb in CATEGORY_ORDER:
            if ca == cb:
                continue
            total = scores_a[ca] + scores_b[cb]
            if total > best:
                best = total
                best_pair = (ca, cb)
    return best, best_pair[0], best_pair[1]


def summarise(values):
    if not values:
        return {}
    vs = sorted(values)
    n = len(vs)
    mean = sum(vs) / n
    median = statistics.median(vs)
    mode_val = Counter(vs).most_common(1)[0][0]
    return {
        "count": n,
        "min": vs[0],
        "max": vs[-1],
        "mean": mean,
        "median": median,
        "mode": mode_val,
        "stdev": statistics.pstdev(vs) if n > 1 else 0.0,
        "sum": sum(vs),
    }


def main():
    payload = json.loads(sys.stdin.read() or "{}")
    state = payload.get("currentState", {}) or {}
    data_file = state.get("data_file")
    if not data_file:
        raise RuntimeError("state.data_file is required (path to the simulation .xlsx)")
    if not os.path.isabs(data_file):
        data_file = os.path.abspath(data_file)

    turns = load_turns(data_file)
    if not turns:
        raise RuntimeError(f"No turn rows parsed from {data_file}")

    per_turn = []
    for t in turns:
        cat_scores = score_turn(t["rolls"])
        best_cat = max(CATEGORY_ORDER, key=lambda c: cat_scores[c])
        per_turn.append({
            "turn": t["turn"],
            "game": t["game"],
            "rolls": t["rolls"],
            "category_scores": cat_scores,
            "best_category": best_cat,
            "best_score": cat_scores[best_cat],
        })

    # Turn-level aggregates
    best_turn_scores = [r["best_score"] for r in per_turn]
    cat_hit_counts = {cat: 0 for cat in CATEGORY_ORDER}
    cat_score_sums = {cat: 0 for cat in CATEGORY_ORDER}
    for r in per_turn:
        for cat in CATEGORY_ORDER:
            s = r["category_scores"][cat]
            cat_score_sums[cat] += s
            # a "hit" means the rule's criteria were met and produced a non-zero
            # score; for the fixed-value categories that's exactly the trigger
            # count; for the open categories every turn is a hit (score > 0)
            if s > 0:
                cat_hit_counts[cat] += 1

    # Group turns into games (keyed by game number, ordered by turn number)
    by_game = {}
    for r in per_turn:
        by_game.setdefault(r["game"], []).append(r)
    games = []
    for g in sorted(by_game.keys()):
        trs = sorted(by_game[g], key=lambda r: r["turn"])
        if len(trs) != 2:
            raise RuntimeError(f"Game {g} does not have exactly 2 turns (has {len(trs)})")
        a, b = trs
        best, ca, cb = best_game_score(a["category_scores"], b["category_scores"])
        games.append({
            "game": g,
            "turn_a": a["turn"],
            "turn_b": b["turn"],
            "best_score": best,
            "category_a": ca,
            "category_b": cb,
        })

    best_game_scores = [g["best_score"] for g in games]

    # Category-usage counts across the best (chosen) category per game turn
    game_category_usage = Counter()
    for g in games:
        game_category_usage[g["category_a"]] += 1
        game_category_usage[g["category_b"]] += 1

    out = {
        "analysis": {
            "turn_count": len(per_turn),
            "game_count": len(games),
            "categories": CATEGORY_ORDER,
            "category_labels": CATEGORY_LABEL,
            "turn_level": {
                "category_score_totals": cat_score_sums,
                "category_hit_counts": cat_hit_counts,
                "best_turn_score_stats": summarise(best_turn_scores),
                "per_category_score_stats": {
                    cat: summarise([r["category_scores"][cat] for r in per_turn])
                    for cat in CATEGORY_ORDER
                },
                "best_category_counts": dict(Counter(r["best_category"] for r in per_turn)),
            },
            "game_level": {
                "best_game_score_stats": summarise(best_game_scores),
                "max_best_game_score": max(best_game_scores),
                "min_best_game_score": min(best_game_scores),
                "game_category_usage": dict(game_category_usage),
                "top_5_games": sorted(
                    games, key=lambda g: g["best_score"], reverse=True
                )[:5],
            },
        },
    }
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
