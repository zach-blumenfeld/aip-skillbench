# Pairing recipes for game-number aggregations

Vectorised pandas patterns for the canonical pair-and-aggregate
questions in `financial-modeling-qa`. Read this when the agent reaches
the `compute-answer` step and needs a starting point.

All recipes assume:

- `df` is the loaded workbook sheet.
- A 1-indexed integer game/trial identifier exists in a column whose
  name you have confirmed (call it `game`).
- An outcome column exists whose semantics the background PDF defines.
  Common shapes: a categorical winner label, a profit/score number,
  paired score columns.

If `game` is not stored as a column but is implied by row order, use
`df.assign(game=range(1, len(df) + 1))` before applying the recipes.

## Recipe 1 — Pair odd-vs-even games into matches

```python
import pandas as pd

odd  = df[df["game"] % 2 == 1].sort_values("game").reset_index(drop=True)
even = df[df["game"] % 2 == 0].sort_values("game").reset_index(drop=True)

# Trim to equal length in case the workbook has a dangling odd game.
n = min(len(odd), len(even))
matches = pd.DataFrame({
    "p1_game":    odd.loc[:n - 1, "game"].values,
    "p2_game":    even.loc[:n - 1, "game"].values,
    "p1_outcome": odd.loc[:n - 1, OUTCOME].values,
    "p2_outcome": even.loc[:n - 1, OUTCOME].values,
})
assert (matches["p2_game"] == matches["p1_game"] + 1).all(), "pairing drift"
```

Now `matches` has one row per match (game 2k-1 vs game 2k). Pick the
recipe below that matches the outcome shape.

## Recipe 2 — Winner-by-label outcome

The outcome column is e.g. `"Win"` / `"Loss"` for the player who played
that game.

```python
p1_wins = (matches["p1_outcome"].str.lower() == "win").sum()
p2_wins = (matches["p2_outcome"].str.lower() == "win").sum()
answer  = int(p1_wins) - int(p2_wins)
```

## Recipe 3 — Winner-by-higher-score outcome

The outcome column is a number; the player with the higher number for
that match wins. Ties don't count for either side unless the background
says otherwise.

```python
p1_wins = (matches["p1_outcome"] >  matches["p2_outcome"]).sum()
p2_wins = (matches["p2_outcome"] >  matches["p1_outcome"]).sum()
answer  = int(p1_wins) - int(p2_wins)
```

## Recipe 4 — Sum-of-metric difference (variant)

If the question is "net P&L of Player 1 minus Player 2" rather than a
win count:

```python
answer = float(matches["p1_outcome"].sum() - matches["p2_outcome"].sum())
```

Cast to `int` only if the background guarantees integer results.

## Writing the answer

```python
from pathlib import Path
Path("/root/answer.txt").write_text(f"{answer}\n")
```

Emit only the number. No labels, no units, no trailing prose. Negative
results stay negative — never wrap in `abs()`.
