#!/usr/bin/env python3
"""Score the ModelOff "Roll The Dice" case: every turn, every game, odd-vs-even matches.

Requires: Python >= 3.8, openpyxl (tested with 3.1.5). pandas is NOT needed.

Usage:
    python scripts/dice_model.py /root/data.xlsx --out-dir /root/dice_out
    options:
      --sheet NAME                 sheet holding the turn table (default: auto-detect "Roll 1" header)
      --two-numbers exact|allow-single
                                   "Only two numbers": exactly two distinct values (default),
                                   or also accept a turn where all six rolls are the same number
      --score-two 30 --score-all 40 --score-run 50 --run-length 4
                                   fixed scores / run length, override only if the background PDF differs
      --allow-missing              continue (with a warning) if turn numbers are still missing after recovery

Writes to --out-dir:
    turns.csv   one row per turn: turn, game, rolls, the six category scores, best turn score + categories
    games.csv   one row per game: both turns, best game score, the chosen category per turn,
                number of distinct optimal assignments
    matches.csv one row per match (game 2k-1 = Player 1 vs game 2k = Player 2) with the winner
    summary.json  data-quality report + headline statistics (also printed to stdout)

Exit codes: 0 ok, 2 data problem that needs a look (message says what), 1 usage error.
"""
import argparse
import csv
import itertools
import json
import os
import statistics
import sys
from collections import Counter

try:
    from openpyxl import load_workbook
except ImportError:
    sys.exit("openpyxl is not installed (pip install openpyxl).")

CATS = ["high_and_often", "summation", "highs_and_lows", "only_two_numbers", "all_the_numbers", "ordered_four"]
CAT_LABEL = {
    "high_and_often": "High and Often",
    "summation": "Summation",
    "highs_and_lows": "Highs and Lows",
    "only_two_numbers": "Only two numbers",
    "all_the_numbers": "All the numbers",
    "ordered_four": "Ordered subset of four",
}


def norm(v):
    return str(v).strip().lower().replace("_", " ") if v is not None else ""


def as_int(v):
    """Integer value of a cell, or None. Accepts 3, 3.0, '3', ' 3 '."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    try:
        f = float(str(v).strip())
        return int(f) if f.is_integer() else None
    except ValueError:
        return None


def find_table(wb, sheet_name):
    sheets = [wb[sheet_name]] if sheet_name else wb.worksheets
    for ws in sheets:
        for row in ws.iter_rows():
            for c in row:
                if norm(c.value) in ("roll 1", "roll1"):
                    hr, rc = c.row, c.column
                    roll_cols = []
                    col = rc
                    while norm(ws.cell(hr, col).value).replace(" ", "") == f"roll{len(roll_cols) + 1}":
                        roll_cols.append(col)
                        col += 1
                    turn_col = game_col = None
                    for cc in range(1, ws.max_column + 1):
                        h = norm(ws.cell(hr, cc).value)
                        if h.startswith("turn"):
                            turn_col = cc
                        elif h.startswith("game"):
                            game_col = cc
                    return ws, hr, turn_col, game_col, roll_cols
    sys.exit("Could not find a header cell 'Roll 1' in any sheet; inspect the workbook and pass --sheet.")


def load_turns(path, sheet_name, allow_missing):
    wb = load_workbook(path, data_only=True)
    ws, hr, turn_col, game_col, roll_cols = find_table(wb, sheet_name)
    n_rolls = len(roll_cols)
    report = {"sheet": ws.title, "header_row": hr, "turn_col": turn_col, "game_col": game_col,
              "roll_cols": roll_cols, "rolls_per_turn": n_rolls, "blank_rows_in_table": [],
              "bad_rows": [], "recovered_rows": [], "stray_cells": [], "duplicates": [],
              "missing_turns": [], "game_number_mismatches": [], "games_without_two_turns": []}
    if turn_col is None:
        report["warning_no_turn_col"] = "No 'Turn number' header; using row order as turn number."
    table_cols = set(roll_cols) | {c for c in (turn_col, game_col) if c}
    turns = {}
    last_data_row = hr
    seq = 0
    for r in range(hr + 1, ws.max_row + 1):
        vals = [ws.cell(r, c).value for c in sorted(table_cols)]
        if all(v is None or str(v).strip() == "" for v in vals):
            report["blank_rows_in_table"].append(r)
            continue
        seq += 1
        last_data_row = r
        t = as_int(ws.cell(r, turn_col).value) if turn_col else seq
        g = as_int(ws.cell(r, game_col).value) if game_col else None
        rolls = [as_int(ws.cell(r, c).value) for c in roll_cols]
        if t is None or any(x is None or not 1 <= x <= 6 for x in rolls):
            report["bad_rows"].append({"row": r, "values": [ws.cell(r, c).value for c in sorted(table_cols)]})
            continue
        if t in turns:
            report["duplicates"].append({"turn": t, "rows": [turns[t]["row"], r]})
            continue
        turns[t] = {"turn": t, "game": g, "rolls": rolls, "row": r}
    report["blank_rows_in_table"] = [r for r in report["blank_rows_in_table"] if r < last_data_row]

    # Every non-empty cell outside the turn table is suspicious: displaced rows hide there.
    width = (2 if game_col else 1) + n_rolls
    for row in ws.iter_rows():
        for c in row:
            if c.value is None or c.row <= hr or c.column in table_cols:
                continue
            report["stray_cells"].append(f"{c.coordinate}={c.value!r}")
    report["stray_cells_total"] = len(report["stray_cells"])
    report["stray_cells"] = report["stray_cells"][:50]
    max_turn = max(turns) if turns else 0
    expected = set(range(1, max(max_turn, 1) + 1))
    if max_turn % 2:
        expected.add(max_turn + 1)
    missing = sorted(expected - set(turns))
    if missing:
        # Look for a horizontal run [turn, (game), roll1..rollN] anywhere on any sheet.
        for sh in wb.worksheets:
            for row in sh.iter_rows():
                cells = [c for c in row]
                for i in range(len(cells) - width + 1):
                    if sh is ws and cells[i].column in table_cols and cells[i].row > hr:
                        continue
                    vals = [as_int(cells[i + k].value) for k in range(width)]
                    if any(v is None for v in vals):
                        continue
                    t = vals[0]
                    g = vals[1] if game_col else None
                    rolls = vals[-n_rolls:]
                    if t in missing and t not in turns and all(1 <= x <= 6 for x in rolls) \
                            and (g is None or g == (t + 1) // 2):
                        turns[t] = {"turn": t, "game": g, "rolls": rolls, "row": None}
                        report["recovered_rows"].append(
                            {"turn": t, "game": g, "rolls": rolls,
                             "from": f"{sh.title}!{cells[i].coordinate}:{cells[i + width - 1].coordinate}"})
        missing = sorted(expected - set(turns))
    report["missing_turns"] = missing

    for t, d in turns.items():
        if d["game"] is None:
            d["game"] = (t + 1) // 2
        elif d["game"] != (t + 1) // 2:
            report["game_number_mismatches"].append({"turn": t, "game": d["game"]})
    by_game = {}
    for t in sorted(turns):
        by_game.setdefault(turns[t]["game"], []).append(turns[t])
    report["games_without_two_turns"] = [g for g, ts in by_game.items() if len(ts) != 2]

    problems = []
    if missing:
        problems.append(f"turn numbers still missing after recovery: {missing[:20]}")
    if report["bad_rows"]:
        problems.append(f"{len(report['bad_rows'])} rows with non-integer or out-of-range values")
    if report["duplicates"]:
        problems.append(f"{len(report['duplicates'])} duplicated turn numbers")
    if report["games_without_two_turns"]:
        problems.append(f"games without exactly two turns: {report['games_without_two_turns'][:20]}")
    return turns, by_game, report, problems


def score_turn(rolls, a):
    hi, lo = max(rolls), min(rolls)
    distinct = len(set(rolls))
    two_ok = distinct == 2 or (a.two_numbers == "allow-single" and distinct == 1)
    run = a.run_length
    has_run = any(
        all(rolls[i + k + 1] - rolls[i + k] == step for k in range(run - 1))
        for i in range(len(rolls) - run + 1) for step in (1, -1))
    return {
        "high_and_often": hi * rolls.count(hi),
        "summation": sum(rolls),
        "highs_and_lows": hi * lo * (hi - lo),
        "only_two_numbers": a.score_two if two_ok else 0,
        "all_the_numbers": a.score_all if sorted(rolls) == list(range(1, 7)) else 0,
        "ordered_four": a.score_run if has_run else 0,
    }


def best_game(s1, s2):
    """Best combined score using a different category for each turn."""
    best, picks = -1, []
    for c1, c2 in itertools.permutations(CATS, 2):
        v = s1[c1] + s2[c2]
        if v > best:
            best, picks = v, [(c1, c2)]
        elif v == best:
            picks.append((c1, c2))
    return best, picks


def describe(values):
    if not values:
        return {}
    c = Counter(values)
    top = max(c.values())
    return {"count": len(values), "sum": sum(values), "mean": statistics.mean(values),
            "median": statistics.median(values), "min": min(values), "max": max(values),
            "mode": sorted(k for k, v in c.items() if v == top), "mode_frequency": top}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("xlsx")
    p.add_argument("--out-dir", default="dice_out")
    p.add_argument("--sheet")
    p.add_argument("--two-numbers", choices=["exact", "allow-single"], default="exact")
    p.add_argument("--score-two", type=int, default=30)
    p.add_argument("--score-all", type=int, default=40)
    p.add_argument("--score-run", type=int, default=50)
    p.add_argument("--run-length", type=int, default=4)
    p.add_argument("--allow-missing", action="store_true")
    a = p.parse_args()

    turns, by_game, report, problems = load_turns(a.xlsx, a.sheet, a.allow_missing)
    if problems and not a.allow_missing:
        print(json.dumps({"status": "data_problem", "problems": problems, "data_report": report}, indent=2, default=str))
        sys.exit(2)
    os.makedirs(a.out_dir, exist_ok=True)

    n = report["rolls_per_turn"]
    turn_rows = []
    for t in sorted(turns):
        d = turns[t]
        d["scores"] = score_turn(d["rolls"], a)
        top = max(d["scores"].values())
        d["best"] = top
        d["best_cats"] = [c for c in CATS if d["scores"][c] == top]
        turn_rows.append([t, d["game"], *d["rolls"], *[d["scores"][c] for c in CATS], top, "|".join(d["best_cats"])])
    with open(os.path.join(a.out_dir, "turns.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["turn", "game", *[f"roll{i}" for i in range(1, n + 1)], *CATS, "best_turn_score", "best_turn_categories"])
        w.writerows(turn_rows)

    games = {}
    game_rows = []
    for g in sorted(by_game):
        ts = by_game[g]
        if len(ts) != 2:
            continue
        t1, t2 = ts
        score, picks = best_game(t1["scores"], t2["scores"])
        games[g] = score
        game_rows.append([g, t1["turn"], t2["turn"], score, picks[0][0], picks[0][1], len(picks)])
    with open(os.path.join(a.out_dir, "games.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["game", "turn_a", "turn_b", "game_score", "category_turn_a", "category_turn_b", "n_optimal_assignments"])
        w.writerows(game_rows)

    p1 = p2 = ties = 0
    unmatched = []
    match_rows = []
    all_games = sorted(by_game)
    last = all_games[-1] if all_games else 0
    for g in range(1, last + 1, 2):
        if g not in games or g + 1 not in games:
            unmatched.append([g, g + 1])
            continue
        s1, s2 = games[g], games[g + 1]
        winner = "player1" if s1 > s2 else "player2" if s2 > s1 else "tie"
        p1 += winner == "player1"
        p2 += winner == "player2"
        ties += winner == "tie"
        match_rows.append([(g + 1) // 2, g, g + 1, s1, s2, winner])
    with open(os.path.join(a.out_dir, "matches.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["match", "game_player1", "game_player2", "score_player1", "score_player2", "winner"])
        w.writerows(match_rows)

    cat_stats = {}
    for c in CATS:
        vals = [turns[t]["scores"][c] for t in turns]
        cat_stats[c] = {"label": CAT_LABEL[c], "turns_scoring_nonzero": sum(v > 0 for v in vals),
                        "total": sum(vals), "max": max(vals), "mean": statistics.mean(vals),
                        "turns_where_best_incl_ties": sum(c in turns[t]["best_cats"] for t in turns),
                        "turns_where_sole_best": sum(turns[t]["best_cats"] == [c] for t in turns)}
    game_cat = Counter()
    for row in game_rows:
        game_cat[row[4]] += 1
        game_cat[row[5]] += 1
    summary = {
        "status": "ok" if not problems else "ok_with_problems",
        "problems": problems,
        "rules": {"two_numbers": a.two_numbers, "score_two": a.score_two, "score_all": a.score_all,
                  "score_run": a.score_run, "run_length": a.run_length,
                  "all_same_turns": sum(len(set(turns[t]["rolls"])) == 1 for t in turns)},
        "data_report": report,
        "n_turns": len(turns), "n_games_scored": len(games),
        "turn_categories": cat_stats,
        "best_turn_score": describe([turns[t]["best"] for t in turns]),
        "game_score": describe(list(games.values())),
        "game_score_distribution": dict(sorted(Counter(games.values()).items())),
        "games_with_multiple_optimal_assignments": sum(r[6] > 1 for r in game_rows),
        "category_use_in_optimal_games_first_assignment": dict(game_cat),
        "matches_odd_vs_even": {"definition": "game 2k-1 (Player 1) vs game 2k (Player 2); higher game score wins; equal = tie",
                                "matches": len(match_rows), "player1_wins": p1, "player2_wins": p2,
                                "ties": ties, "player1_minus_player2": p1 - p2, "unmatched_matches": unmatched},
        "outputs": {k: os.path.join(a.out_dir, k) for k in ("turns.csv", "games.csv", "matches.csv", "summary.json")},
    }
    with open(os.path.join(a.out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
