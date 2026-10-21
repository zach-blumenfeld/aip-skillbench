Answer this question about the Roll The Dice case: {question}

Every turn and game is already scored. Standard results: {dice_stats}
Data issues found and repaired while loading: {dice_data_issues}
Per-turn scores: {dice_turns_csv}   Per-game best scores: {dice_games_csv}

1. Read references/dice-case-rules.md (interpretations, CSV columns, which stat answers which question pattern).
2. If a precomputed stat answers the question exactly as worded, use it. Otherwise compute it with pandas from the two CSVs (python3 with pandas is available); never re-derive scores from the raw workbook.
3. Check the question's own definitions (pairing, tie handling, which category, thresholds) against the stat's rule text before using it; recompute when they differ.
4. If the question is multiple choice, pick the option matching the computed value.

Return `dice_answer`: only the final value as the question wants it written (for "only write the number": just the number, no units, no words).
