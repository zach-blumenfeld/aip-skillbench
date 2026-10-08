# Dice-scoring case notes ("Roll The Dice", ModelOff 2016 R1 S3)

Load this when a question is ambiguous about the denominator, ties, or rule edge cases, or when no multiple-choice option matches.

## Case structure
- 6,000 simulated turns = 3,000 games x 2 turns. Each turn = 6 rolls of one die, in the order rolled.
- Questions 20-26 use turn results only. Questions 27-29 use game results. Questions 20-27 are multiple choice. Questions 28-29 take a typed number. Question 30 is uploading the workbook.
- Turn score per category: High and Often = highest x count of highest. Summation = sum. Highs and Lows = highest x lowest x (highest - lowest), which is 0 when every roll is the same. Only two numbers = 30. All the numbers (1-6 in any order) = 40. Ordered subset of four = 50.
- Game score = highest combined score of its two turns with the two turns in DIFFERENT categories: max over c1 != c2 of turn1[c1] + turn2[c2]. Taking each turn's own best, when both are the same category, overstates the score.

## Workbook traps (the loader handles these; know them when answering)
- The data sheet is "Data", header row 9, columns C:J (Turn number, Game number, Roll 1-6). Other sheets ("Formats") are style legends, not data.
- At least one record has been moved out of the table, leaving a blank row. Turn 15 sat at N37:U37 in the original file. A plain `pd.read_excel` + `dropna` silently loses it: 5,999 turns, and one game with a single turn. Always check `data_issues`. Never re-read the raw sheet yourself.

## Question-reading checklist
- "Average score for category X": over all turns (zeros included) unless it says "of turns that score" or "when achieved". Both are in the summary: `mean` vs `mean_when_nonzero`.
- "How many turns can score in X": `turns_scoring_nonzero`. The any-turn categories always score, except Highs and Lows on an all-equal turn.
- "Highest possible score for a turn": `best_turn_score`, the max over categories. "Most common best category" counts ties separately (`turns_where_sole_best_category` vs `turns_where_best_category`).
- "Total / average / median / max game score": `game_score_stats`. "How many games score above N": count in `games.csv`, and watch "above" vs "at least".
- "How often is category X used in the games": ties make it ambiguous. Report the unique-optimal count and the number of tied games.
- Score frequency or distribution questions: use the `distribution` maps (keys are scores as strings).
