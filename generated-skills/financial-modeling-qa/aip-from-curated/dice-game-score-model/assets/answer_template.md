# Dice-game analysis — answer

**Workbook:** {data_file}
**Turns analysed:** {analysis[turn_count]}
**Games analysed:** {analysis[game_count]}

## Question
{question}

## Answer
Write a direct, numeric answer to the question above. Pull every figure from
the `analysis` object in state (also summarised below) — do not re-derive from
the raw rolls. Round only when the question asks for it, and name the units
(turn score, game score, count, percentage).

If the question refers to a specific category, use the keys from
`analysis.categories` and the pretty labels from `analysis.category_labels`.

If the question is multiple-choice, state the chosen letter/number **and** the
figure it corresponds to.

## Key figures from the computed analysis
- Best **turn** score — mean {analysis[turn_level][best_turn_score_stats][mean]:.4f},
  median {analysis[turn_level][best_turn_score_stats][median]},
  max {analysis[turn_level][best_turn_score_stats][max]},
  stdev {analysis[turn_level][best_turn_score_stats][stdev]:.4f}.
- Best **game** score — mean {analysis[game_level][best_game_score_stats][mean]:.4f},
  median {analysis[game_level][best_game_score_stats][median]},
  max {analysis[game_level][max_best_game_score]},
  min {analysis[game_level][min_best_game_score]}.
- Category hit counts across all turns (how often each rule's criteria were
  met with a non-zero score): see `analysis.turn_level.category_hit_counts`.
- How often each category was the best scoring category for a turn:
  `analysis.turn_level.best_category_counts`.
- Category usage across the chosen best-game assignments (two per game):
  `analysis.game_level.game_category_usage`.

Load `references/scoring-rules.md` if you need to recheck a category's rule
before answering.
