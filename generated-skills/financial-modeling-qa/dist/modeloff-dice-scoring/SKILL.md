---
name: modeloff-dice-scoring
description: Answers ModelOff "Roll The Dice" financial-modeling case questions from a workbook of simulated dice turns (data.xlsx) plus a background PDF of scoring rules. Scores every turn in six categories (High and Often, Summation, Highs and Lows, Only two numbers, All the numbers, Ordered subset of four), finds each game's best two-turn score with no category reused, compares odd vs even games as player matches, recovers displaced or blank data rows, and writes a numeric answer file. Use for dice-game scoring, turn/game statistics, or Player 1 vs Player 2 match counts on a ModelOff-style xlsx + pdf task.
compatibility: Python >= 3.8; pip packages openpyxl (tested 3.1.5) and pypdf (tested 5.1.0); pandas 2.x optional for custom follow-up queries. No LibreOffice, pdfplumber, or poppler needed.
---

# ModelOff Dice Case Scoring

## Trigger When

- A task gives a workbook of dice rolls (turn number, game number, Roll 1..Roll 6) and a background PDF titled like "Case Study – Roll The Dice" (ModelOff 2015/2016 Round 1 Section 3).
- The question asks for a count, total, max, average, or difference over turn scores, game scores, scoring categories, or matches between players (e.g. odd games = Player 1, even games = Player 2).
- More broadly: any "analyze a large xlsx with a rules PDF and write one number to answer.txt" task whose rules are dice-turn scoring categories with a best-combination game score.

## Purpose

Turns the case's scoring rules into a tested, deterministic model: a loader that finds the turn table wherever it sits and repairs planted data defects (blank rows, a turn moved off to stray cells), a per-turn scorer for all six categories, an exact best-assignment game scorer (two turns, two different categories), and the odd-vs-even match tally — then maps the question onto those outputs and writes only the number. It adds the case rules, the interpretation choices, and the data traps an agent would otherwise miss.

## Before the first script

Check that `python3` runs and that `python3 -c "import openpyxl, pypdf"` succeeds. If anything is missing, name every missing item at once, then install it (`pip install --break-system-packages openpyxl pypdf`) or report it. Run commands from the skill folder; write working files under a scratch dir such as `/root/dice_out/`, never inside the skill folder.

## Procedure

Progress:
- [ ] 1. Extract the rules (script)
- [ ] 2. Check the rules and classify the question (decision)
- [ ] 3. Build the model (script)
- [ ] 4. Review the data report (decision)
- [ ] 5. Answer the question (client task)
- [ ] 6. Write and verify the answer file

### 1. Extract the rules — `execution`

```bash
python3 scripts/extract_pdf_text.py /root/background.pdf /root/dice_out/background.txt
```

Input: PDF path. Output: page-by-page text (stdout and the optional txt). "Ignoring wrong pointing object" warnings are harmless. If a page reports no extractable text, take the rules from the question text and the table below.

### 2. Check the rules and classify the question — `decision`

Input: the extracted PDF text and the question. The defaults the model script implements:

| Category | Qualifies | Score (script flag) |
|---|---|---|
| High and Often | any turn | highest roll × times it was rolled |
| Summation | any turn | sum of the six rolls |
| Highs and Lows | any turn | highest × lowest × (highest − lowest) |
| Only two numbers | all six rolls are one of exactly two values (3-6-3-6-6-6) | 30 (`--score-two`) |
| All the numbers | rolls are 1-2-3-4-5-6 in any order | 40 (`--score-all`) |
| Ordered subset of four | 4 adjacent rolls, in rolled order, each +1 or each −1 (1-2-3-4, 5-4-3-2) | 50 (`--score-run`, `--run-length 4`) |

A non-qualifying turn scores 0 in that category. Game score = max over the two turns of (category A score of turn 1 + category B score of turn 2), A ≠ B.

```yaml
rules_match_defaults:
  type: noul
  instructions: Do the PDF's categories, criteria, fixed scores, and game rule match the table above exactly?
  criteria:
    true: Same six categories, same formulas, same fixed scores, same run length, 2 turns per game, no category reused.
    false: Any score value, run length, criterion, or the game rule differs, or a category is added or removed.
  costly_mistake: a false "true" silently scores everything wrong; reread the table row by row on any doubt.
question_scope:
  type: choice
  instructions: What does the question measure?
  criteria:
    matches: Players/matches built from games (odd vs even, game 1 vs game 2, wins, losses, ties).
    turn: Turn-level scores or categories (how many turns qualify for X, highest turn score, best category per turn).
    game: Game-level best scores (total, average, max, count above a threshold, most common score, categories used).
    other: Anything else (different pairing, rolls-only statistics, a probability).
```

Act on the answers:
- `rules_match_defaults = false` and only numbers differ → pass the matching flags in step 3. If a criterion or the game rule itself differs, copy `scripts/dice_model.py` to the scratch dir, edit `score_turn` / `best_game` to the PDF's rule, and run the copy.
- Keep `question_scope` for step 5.

### 3. Build the model — `execution`

```bash
python3 scripts/dice_model.py /root/data.xlsx --out-dir /root/dice_out [--two-numbers allow-single] [--score-two N --score-all N --score-run N --run-length N] [--sheet NAME]
```

Input: the workbook. Output (in `--out-dir`, and `summary.json` echoed to stdout):
- `turns.csv` — turn, game, rolls, the six category scores, `best_turn_score`, `best_turn_categories` (ties joined by `|`).
- `games.csv` — game, its two turns, `game_score`, one optimal category per turn, `n_optimal_assignments`.
- `matches.csv` — match k = game 2k−1 (Player 1) vs game 2k (Player 2), both scores, winner (`tie` when equal).
- `summary.json` — `data_report`, `rules`, per-category stats, `best_turn_score` and `game_score` stats, `game_score_distribution`, `matches_odd_vs_even` with `player1_minus_player2`.

Exit 2 with `"status": "data_problem"` means the table has defects the loader could not repair (missing turns, non-integer or out-of-range rolls, duplicates, a game without two turns); go to step 4 with that report. Only add `--allow-missing` after step 4 decides the gap is genuine.

### 4. Review the data report — `decision`

Input: `data_report` and `rules.all_same_turns` from step 3.

```yaml
data_trustworthy:
  type: noul
  instructions: Does the loaded table cover every turn exactly once with valid rolls, so the outputs can be used as-is?
  criteria:
    true: missing_turns, bad_rows, duplicates, games_without_two_turns are empty; every stray cell is explained by a recovered_rows entry; n_turns = 2 × n_games_scored.
    false: Any of those lists is non-empty, or stray_cells holds numbers no recovered row accounts for.
  costly_mistake: a false "true" — a dropped or displaced turn changes match and game counts and the final answer.
two_numbers_single:
  type: noul
  instructions: Only answer when rules.all_same_turns > 0 (otherwise the answer is false and moot). Does the PDF's "Only two numbers" wording also accept a turn whose six rolls are all the same number?
  criteria:
    true: The wording says "at most two" numbers or explicitly includes a single repeated number.
    false: The wording requires two numbers ("all one of two numbers", e.g. 3-6-3-6-6-6) — the default.
```

- `data_trustworthy = false` → open the cells named in the report (`openpyxl.load_workbook(path, data_only=True)`; rows/cols are 1-based) and repair: if a turn's values sit elsewhere in a layout the loader did not match, copy the workbook to scratch, put the values back on the blank row, rerun step 3 on the copy. Rerun step 4 after any repair.
- `two_numbers_single = true` → rerun step 3 with `--two-numbers allow-single`.

### 5. Answer the question — `client_task`

Input: `question_scope`, `summary.json`, the CSVs. Output: one number.

Read straight from `summary.json` when the question is one of these:

| Question asks | Field |
|---|---|
| (Player 1 match wins) − (Player 2 match wins), odd vs even games | `matches_odd_vs_even.player1_minus_player2` |
| Player 1 / Player 2 wins, ties | `matches_odd_vs_even.player1_wins` / `player2_wins` / `ties` |
| turns that qualify for / score in category X | `turn_categories.<x>.turns_scoring_nonzero` |
| highest / total / average score in category X | `turn_categories.<x>.max` / `total` / `mean` |
| turns where X gives the highest score | `turn_categories.<x>.turns_where_best_incl_ties` (or `turns_where_sole_best` if ties must be excluded) |
| highest, lowest, total, average, median, most common game score | `game_score.max` / `min` / `sum` / `mean` / `median` / `mode` |
| games scoring exactly S | `game_score_distribution["S"]` |

Otherwise compute it from the CSVs with pandas, e.g. games ≥ 60: `(pd.read_csv('/root/dice_out/games.csv').game_score >= 60).sum()`; a different player pairing: rebuild from `games.csv` the way `matches.csv` is built (ties win for nobody unless the question says otherwise). Sanity-check the chosen value against one or two rows you score by hand from `turns.csv`.

### 6. Write and verify the answer file

Write only the number, no label or units, e.g. `printf '%s\n' <value> > /root/answer.txt`. Integers without decimals; keep the sign for differences; round non-integers only as the question asks (otherwise 2 decimals). If the question lists multiple-choice options, still write the computed number (not an option letter) unless told otherwise. Then `cat /root/answer.txt` to confirm.

## Gotchas

- The reference workbook hides one turn: its table row is blank and the eight values (turn, game, 6 rolls) sit in stray cells several columns to the right of the table. The loader recovers such rows by matching turn number, game = ⌈turn/2⌉, and rolls 1–6; always confirm `recovered_rows` and `stray_cells` agree.
- The header is not on row 1 (title rows above, data starting in column C); the loader finds it by the `Roll 1` header, so do not hardcode cell offsets in custom code either.
- The workbook stores values, not formulas; there is no LibreOffice in the container, so do not try to recalc. If you write a model workbook, never save a file opened with `data_only=True` over the original.
- Summation always beats High and Often (the sum contains highest × count plus the other rolls), so High and Often is rarely in an optimal assignment; that is expected, not a bug.
- Ties: a match with equal game scores is won by nobody; a turn's best category may be tied — the CSV lists all.
- Read [references/reading-xlsx-pdf.md](references/reading-xlsx-pdf.md) only if you must write custom pandas/openpyxl/pypdf code (layout quirks, loaders, what is not available in the container).
