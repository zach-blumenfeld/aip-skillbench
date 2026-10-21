# Roll The Dice case: rules, interpretations, outputs

Load when answering any question on the dice branch, or when a question hinges on how a rule is read.

## Rules (from the case pack)

- A game = 2 turns. A turn = one six-sided die rolled 6 times, order recorded.
- Turn categories (score):
  | Category | Applies | Score |
  |---|---|---|
  | High and Often | any turn | highest roll x number of times it was rolled |
  | Summation | any turn | sum of the six rolls |
  | Highs and Lows | any turn | highest x lowest x (highest - lowest) |
  | Only two numbers | all six rolls are one of two numbers (3-6-3-6-6-6) | 30 |
  | All the numbers | rolls are 1-2-3-4-5-6 in any order | 40 |
  | Ordered subset of four | in roll order, a run of 4 consecutive increasing or decreasing numbers (1-2-3-4, 5-4-3-2) | 50 |
- Game score = highest combined score of the two turns where the two turns use **different** categories.
- Fixed scores (30/40/50) are read from the background text; `dice_stats.fixed_scores_source` says whether a default was used. If a default was used and the background shows other values, rescore with the corrected values.

## Interpretations the script applies

- Ordered run = 4 **adjacent** positions with step +1 throughout or -1 throughout (1-2-3-4 yes; 1-2-4-5 no; 1-3-2-4 no).
- Only two numbers = exactly 2 distinct values. All six identical (1 distinct) does not qualify. `turns_qualifying.only_two_numbers` counts the exactly-2 case; if a question's reading differs and the data has all-same turns, recount from `dice_turns.csv`.
- Highs and Lows is 0 when all rolls are equal (difference 0).
- Non-qualifying fixed categories score 0; since every score is >= 0, choosing a 0 category never beats an alternative, so 0 is safe.
- Game pairing uses the **Game number** column, never row position.

## Data traps

- A turn record can be cut from its row and pasted elsewhere (e.g. to columns N:U on another row), leaving a blank row in the table. Reading only the main columns, or `dropna`, silently loses that turn and shifts every positional pairing after it. The script scans every sheet for 8-cell turn records and rebuilds by turn number; check `dice_data_issues`.
- Numbers stored as text are coerced; conflicting duplicate turn records keep the first and are reported.
- If `dice_data_issues` reports missing turns or games without 2 turns, say so; do not invent rolls.

## Output files (work_dir)

`dice_turns.csv`: turn, game, roll1..roll6, high_and_often, summation, highs_and_lows, only_two_numbers, all_the_numbers, ordered_four, best_single_category_score.

`dice_games.csv`: game, turn_a, turn_b, game_score, cat_turn_a, cat_turn_b (first optimal assignment, category order above), n_optimal_assignments, optimal_assignments (all `a+b` pairs reaching the max).

## Question patterns -> where the answer is

- "How many turns score in X / qualify for X" -> `dice_stats.turns_qualifying` or value counts; for a threshold, filter `dice_turns.csv`.
- "Average / total / max score of category X" -> `turn_category_means|totals|max`.
- "Most common / highest / lowest / average game score", "how many games score N" -> `game_score_*`.
- "Which category is used most in the best game score" -> `dice_games.csv` cat columns, but when `n_optimal_assignments > 1` the choice is ambiguous: count all optimal assignments or state the tie.
- Players / matches: odd games = Player 1, even = Player 2, match k = game 2k-1 vs game 2k, higher game score wins, equal scores are a tie that counts for neither -> `odd_vs_even_matches`. If the question defines matches differently (other pairing, turn-level scores, ties counted), recompute from `dice_games.csv`.
- Multiple-choice questions: compute the value, then pick the option equal to it; if none matches, recheck interpretations above before answering.
