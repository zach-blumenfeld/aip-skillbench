# Answer the finance QA question

## The question
{question}

## Background PDF (extracted text)
{background_text}

## Data file summary (data_path = `{data_path}`)
```json
{data_summary}
```

## Your task

Compute the numeric answer to the question above by combining the background rules with the raw data. Then return JSON on stdout:

```json
{{"answer": "<the number>"}}
```

The `answer` string must match `^-?\d+(\.\d+)?$` — integer or decimal, optional leading minus, nothing else (no units, no commas, no thousand separators, no trailing text). The `write-answer` step will reject anything else and refuse to save.

## Method — do all of it, in order

1. **Reread the background PDF text above until you can restate every rule, formula, and constant it defines in your own words.** The background usually encodes non-obvious scoring or classification logic that the raw data alone cannot tell you (e.g., how a "score" is computed, what counts as a "win", what a numeric bonus is). If any rule is ambiguous, pick the reading that fits the data structure and write down which one you picked.
2. **Re-read the data summary above** and identify:
   - which sheet holds the answer data (usually the one whose columns match the entities the question names);
   - which columns are the key identifiers (game/turn/row id, player, roll, etc.) — do not assume they are consecutive or in header row 0; header rows may be nested or offset;
   - which columns carry the numeric values you need.
3. **Write a Python script** that reads `{data_path}` and computes the answer. Save it to `/tmp/finance_qa_solution.py`, then run `python3 /tmp/finance_qa_solution.py` and read its stdout.
   - Use `pandas` (installed) with `pd.read_excel(..., header=None, dtype=object)` when column locations are uncertain, then coerce column-by-column with `pd.to_numeric(..., errors="coerce")`; this survives stray strings, blanks, and header rows mixed into the data.
   - Use `openpyxl` (installed) only if you need cell formatting or formulas — for pure value analysis, pandas is faster.
   - Detect the relevant columns programmatically when the header names are missing or unclear: e.g., "the six columns whose values are integers in [1..6]" for dice rolls, or "the column where each id appears exactly twice" for a game id when each game has two turns.
   - Guard against div-by-zero, empty groups, and off-by-one errors. Excel is 1-indexed; pandas is 0-indexed.
   - When the question names a specific matchup rule (e.g., "odd game vs even game"), iterate matches deterministically (`for m in range(1, max_game // 2 + 1): g1, g2 = 2*m - 1, 2*m`) rather than by row order.
4. **Sanity-check the number** before returning it:
   - It should have the sign the question implies (a "difference" can be negative; a "count" cannot).
   - Recompute it with an alternative formulation if you can (e.g., `sum(p1_wins) - sum(p2_wins)` vs `sum(1 for m in matches if winner(m) == 'p1') - sum(1 for m in matches if winner(m) == 'p2')`).
   - If the two methods disagree, debug before answering.
5. Print the JSON object `{{"answer": "<number>"}}` and nothing else on the line the client parses.

## Gotchas

- The background PDF may include a **specific missing row / correction** or a "known-good" example that the raw data does not contain. If the background says "turn X of game Y is missing, insert the following rolls," honor it: build the row and concat it into your DataFrame before computing scores.
- pypdf's text extraction can drop whitespace and reflow tables. If the extracted background text looks garbled around a formula, re-open the PDF layout in your head from context — the numbers are usually right even if the spacing is off.
- Do not round unless the question explicitly says so. If the true answer is an integer, print it without a decimal point; if it is a float, print enough decimals to be exact (at least 6 significant digits) — verifiers typically accept a tight numeric tolerance, not textual equality.
- Do not write to `answer_path` yourself — the `write-answer` step does that after validating the format.
