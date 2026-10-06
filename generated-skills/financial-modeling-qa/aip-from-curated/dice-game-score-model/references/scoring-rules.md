# Dice-game scoring reference

Source: ModelOff 2016 Round 1 Section 3 — "Roll The Dice" case pack (see
`source/environment/background.pdf`). This file is the agent's bedside copy of
the rules the compute script enforces; load it when drafting the answer or when
sanity-checking a result.

## Game structure
- A **game** has 2 **turns**.
- A **turn** is six rolls of one six-sided die, recorded in the order rolled.
- A turn can score under each category listed below; the turn's own score is
  the maximum across categories.
- A game's score is the highest total obtainable by assigning each of its two
  turns to a **different** category and summing the two category scores
  (no category may be used twice in the same game).

## Scoring categories

| Key                       | Label                   | Criteria                                                             | Score                                                   |
|---------------------------|-------------------------|----------------------------------------------------------------------|---------------------------------------------------------|
| `high_and_often`          | High and Often          | Always applies.                                                      | highest roll × number of times it appears in the turn    |
| `summation`               | Summation               | Always applies.                                                      | sum of all six rolls                                     |
| `highs_and_lows`          | Highs and Lows          | Always applies.                                                      | highest × lowest × (highest − lowest)                    |
| `only_two_numbers`        | Only two numbers        | All six rolls are one of only two distinct face values (e.g. 3-6-3-6-6-6). | 30                                                       |
| `all_the_numbers`         | All the numbers         | The six rolls are 1,2,3,4,5,6 in any order (one of each).            | 40                                                       |
| `ordered_subset_of_four`  | Ordered subset of four  | In rolled order, there is a window of 4 consecutive positions whose values are either strictly +1 each step (e.g. 1-2-3-4) or strictly −1 each step (e.g. 5-4-3-2). | 50                                                       |

Notes:
- A fixed-value category (`only_two_numbers`, `all_the_numbers`,
  `ordered_subset_of_four`) scores zero when its criteria are not met.
- "Only two numbers" is satisfied when the turn's set of distinct faces has
  size ≤ 2 (one unique face still counts — it is a strict subset of two).
- "Ordered subset of four" cares about rolled order and only awards once per
  turn regardless of how many qualifying windows exist.
- The best turn score is the maximum of all six category scores.
- The best game score is `max over (a,b with a≠b) of
  turn1.category_scores[a] + turn2.category_scores[b]`.

## Expected workbook layout
- Sheet named `Data` (fall back to the first sheet otherwise).
- A header row contains the labels `Turn number`, `Game number`,
  `Roll 1` … `Roll 6`. The compute script finds this row by name, so extra
  cosmetic rows above or below do not matter.
- Data rows below the header carry one turn per row; turns are grouped into
  games of exactly 2 by `Game number`.
