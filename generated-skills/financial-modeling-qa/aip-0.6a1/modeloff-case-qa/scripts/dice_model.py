"""Score every turn and game of the 'Roll The Dice' case and precompute standard answers.

stdin: {"state": {"data_path", "background_text", "work_dir"}, ...}
stdout: {"dice_turns_csv", "dice_games_csv", "dice_stats", "dice_data_issues"}

Loader: the turn table is a block of [Turn number, Game number, Roll 1..Roll 6]. Records can
be displaced (cut out of their row and pasted elsewhere, e.g. off to the right), stored as
text, or blank. Every sheet is scanned for 8-cell runs that look like a turn record and the
table is rebuilt by turn number, so no record is lost and nothing shifts game pairings.
"""
import collections
import itertools
import json
import os
import re
import sys

import openpyxl
import pandas as pd

CATS = ["high_and_often", "summation", "highs_and_lows", "only_two_numbers",
        "all_the_numbers", "ordered_four"]
FIXED_DEFAULT = {"only_two_numbers": 30, "all_the_numbers": 40, "ordered_four": 50}
FIXED_PATTERNS = {
    "only_two_numbers": r"Only\s+two\s+numbers.*?\)\s*(\d+)",
    "all_the_numbers": r"All\s+the\s+numbers.*?6\s*(\d+)\s",
    "ordered_four": r"Ordered\s+subset\s+of\s+four.*?\)\s*(\d+)",
}


def fixed_scores(text):
    out, src = {}, {}
    flat = " ".join(text.split())
    for cat, pat in FIXED_PATTERNS.items():
        m = re.search(pat, flat, re.I)
        out[cat] = int(m.group(1)) if m else FIXED_DEFAULT[cat]
        src[cat] = "background" if m else "default"
    return out, src


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def load_records(path, issues):
    wb = openpyxl.load_workbook(path, data_only=True)
    recs = {}
    header_loc = None
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        for i, r in enumerate(rows):
            labels = [str(c).strip().lower() if c is not None else "" for c in r]
            if header_loc is None and "roll 1" in labels:
                header_loc = (ws.title, i + 1, labels.index("roll 1") - 2)
        for i, r in enumerate(rows):
            vals = [num(c) for c in r]
            j = 0
            while j + 8 <= len(vals):
                block = vals[j:j + 8]
                if all(v is not None for v in block) and all(float(v).is_integer() for v in block) \
                        and all(1 <= v <= 6 for v in block[2:]) and block[0] >= 1 and block[1] >= 1:
                    turn, game = int(block[0]), int(block[1])
                    rolls = [int(v) for v in block[2:]]
                    if any(isinstance(c, str) for c in r[j:j + 8]):
                        issues.append(f"{ws.title}!row {i + 1}: turn {turn} stored as text; coerced to numbers")
                    loc = (ws.title, i + 1, j)
                    if turn in recs and recs[turn]["rolls"] != rolls:
                        issues.append(f"turn {turn}: conflicting records at {recs[turn]['loc']} and {loc}; kept first")
                    elif turn in recs:
                        issues.append(f"turn {turn}: duplicate identical record at {loc}; ignored")
                    else:
                        recs[turn] = {"turn": turn, "game": game, "rolls": rolls, "loc": loc}
                    j += 8
                else:
                    j += 1
    if header_loc is None:
        raise SystemExit("no 'Roll 1' header found in any sheet; this is not the dice-turn table layout")
    hs, hrow, hcol = header_loc
    for t, rec in sorted(recs.items()):
        s, rn, c = rec["loc"]
        if s != hs or c != hcol or rn <= hrow:
            col = openpyxl.utils.get_column_letter(c + 1)
            issues.append(f"turn {t} (game {rec['game']}) found displaced at {s}!{col}{rn}, not in the "
                          f"main table columns; reinserted by turn number")
    return recs


def run_of_four(r):
    for i in range(len(r) - 3):
        d = {r[i + k + 1] - r[i + k] for k in range(3)}
        if d == {1} or d == {-1}:
            return True
    return False


def score_turn(r, fixed):
    hi, lo = max(r), min(r)
    distinct = len(set(r))
    return {
        "high_and_often": hi * r.count(hi),
        "summation": sum(r),
        "highs_and_lows": hi * lo * (hi - lo),
        "only_two_numbers": fixed["only_two_numbers"] if distinct == 2 else 0,
        "all_the_numbers": fixed["all_the_numbers"] if sorted(r) == [1, 2, 3, 4, 5, 6] else 0,
        "ordered_four": fixed["ordered_four"] if run_of_four(r) else 0,
    }


def best_game(a, b):
    best, combos = -1, []
    for ca, cb in itertools.permutations(CATS, 2):
        s = a[ca] + b[cb]
        if s > best:
            best, combos = s, [(ca, cb)]
        elif s == best:
            combos.append((ca, cb))
    return best, combos


def match_stats(games, odd_first=True):
    by = dict(zip(games["game"], games["game_score"]))
    w1 = w2 = ties = 0
    unpaired = []
    for g in sorted(by):
        if g % 2 == 1:
            if g + 1 not in by:
                unpaired.append(g)
                continue
            s1, s2 = by[g], by[g + 1]
            w1 += s1 > s2
            w2 += s2 > s1
            ties += s1 == s2
    return {"rule": "game 2k-1 (Player 1, odd) vs game 2k (Player 2, even); higher game score wins; equal = tie, no winner",
            "player1_wins": w1, "player2_wins": w2, "ties": ties,
            "player1_minus_player2": w1 - w2, "matches": w1 + w2 + ties, "unpaired_odd_games": unpaired}


def main():
    state = json.load(sys.stdin)["state"]
    issues = []
    fixed, fixed_src = fixed_scores(state.get("background_text", ""))
    recs = load_records(state["data_path"], issues)
    turns = sorted(recs)
    missing = sorted(set(range(1, max(turns) + 1)) - set(turns))
    if missing:
        issues.append(f"turn numbers missing entirely (not found anywhere): {missing[:20]}")
    rows = []
    for t in turns:
        r = recs[t]["rolls"]
        rows.append({"turn": t, "game": recs[t]["game"], **{f"roll{i + 1}": v for i, v in enumerate(r)},
                     **score_turn(r, fixed)})
    td = pd.DataFrame(rows)
    td["best_single_category_score"] = td[CATS].max(axis=1)
    sizes = td.groupby("game").size()
    bad = sizes[sizes != 2]
    if len(bad):
        issues.append(f"games without exactly 2 turns: {bad.to_dict() if len(bad) < 20 else len(bad)}")
    games = []
    for g, grp in td.groupby("game"):
        if len(grp) != 2:
            continue
        a, b = grp.iloc[0], grp.iloc[1]
        score, combos = best_game(a, b)
        games.append({"game": int(g), "turn_a": int(a["turn"]), "turn_b": int(b["turn"]), "game_score": int(score),
                      "cat_turn_a": combos[0][0], "cat_turn_b": combos[0][1], "n_optimal_assignments": len(combos),
                      "optimal_assignments": ";".join(f"{x}+{y}" for x, y in combos)})
    gd = pd.DataFrame(games)
    os.makedirs(state["work_dir"], exist_ok=True)
    tpath = os.path.abspath(os.path.join(state["work_dir"], "dice_turns.csv"))
    gpath = os.path.abspath(os.path.join(state["work_dir"], "dice_games.csv"))
    td.to_csv(tpath, index=False)
    gd.to_csv(gpath, index=False)

    gs = gd["game_score"]
    stats = {
        "fixed_scores_used": fixed, "fixed_scores_source": fixed_src,
        "n_turns": len(td), "n_games_scored": len(gd),
        "turn_category_totals": {c: int(td[c].sum()) for c in CATS},
        "turn_category_means": {c: round(float(td[c].mean()), 6) for c in CATS},
        "turn_category_max": {c: int(td[c].max()) for c in CATS},
        "turns_qualifying": {c: int((td[c] > 0).sum()) for c in CATS[3:]},
        "turn_category_value_counts": {c: {int(k): int(v) for k, v in td[c].value_counts().sort_index().items()}
                                       for c in CATS[:3]},
        "game_score_total": int(gs.sum()), "game_score_mean": round(float(gs.mean()), 6),
        "game_score_median": float(gs.median()), "game_score_max": int(gs.max()), "game_score_min": int(gs.min()),
        "game_score_mode": [int(x) for x in gs.mode()],
        "game_score_value_counts": {int(k): int(v) for k, v in gs.value_counts().sort_index().items()},
        "games_with_max_score": gd.loc[gs == gs.max(), "game"].tolist()[:50],
        "games_with_tied_optimal_assignment": int((gd["n_optimal_assignments"] > 1).sum()),
        "odd_vs_even_matches": match_stats(gd),
    }
    json.dump({"dice_turns_csv": tpath, "dice_games_csv": gpath, "dice_stats": stats,
               "dice_data_issues": issues}, sys.stdout)


if __name__ == "__main__":
    main()
