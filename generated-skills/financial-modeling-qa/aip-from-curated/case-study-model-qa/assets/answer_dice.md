Answer the question from the scored dice model.

Question:
{question}

Expected answer format: {answer_format}

Scoring summary (computed by scripts/score_dice.py from every turn in the workbook):
{dice_summary}

Data issues the loader found and handled:
{data_issues}

Full results to query when the summary does not hold the number directly:
- Per-turn table: {turns_csv}. Columns: turn, game, roll1..roll6, source_cell, one score column per category id, best_turn_score, best_turn_categories.
- Per-game table: {games_csv}. Columns: game, turn1, turn2, turnN_category, turnN_points, game_score, n_optimal_assignments, all_optimal_assignments.

Do this:
1. Restate exactly what the question measures: turn level or game level? Which category? Count, total, average, maximum, or a share? Does it cover all turns, or only the turns where a category scores (nonzero)? Which turn or game numbers, if it names any?
2. Read the number from `dice_summary` when it is there directly. Otherwise compute it from the CSVs with pandas, e.g. `python3 -c "import pandas as pd; t=pd.read_csv('<turns_csv>'); print((t.summation>t.highs_and_lows).sum())"`. Never recompute scores by hand, and never re-read the raw workbook, which has displaced records the loader already fixed.
3. Turn-level questions use the per-category scores of single turns. Game-level questions use `game_score`, the best total with each turn in a different category. "Which category is used" in a game is ambiguous when `n_optimal_assignments` > 1. Report `category_in_unique_optimal_assignment_games` and say how many games tie.
4. Averages: say whether you divided by all turns or games, or only by the turns where a category scores. Use the one the question's wording implies. If it is ambiguous, give the all-turns figure first.
5. Multiple choice: pick the option equal to your computed value. Round only for comparison, at the precision the options show. If no option matches, recheck step 1, rule edge cases, and the data issues before choosing the closest option. Then put the computed value and its gap to the chosen option in `answer` itself, e.g. "A) 92 (computed 74; no option matches)".
6. Output `answer`, the final answer as the question wants it (the option letter and value, or the number), and `working`, a few lines: what you computed, from which column or summary field, the denominator, and any data issue that affected it.
