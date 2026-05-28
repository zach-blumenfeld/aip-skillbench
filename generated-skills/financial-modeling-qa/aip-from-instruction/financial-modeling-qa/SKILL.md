---
name: financial-modeling-qa
description: Answer a numeric analytical question about a large financial-modeling spreadsheet (/root/data.xlsx) paired with a context PDF (/root/background.pdf), then write only the answer value to /root/answer.txt. Use when the task ships a data.xlsx, a background.pdf, and asks for a single numeric value derived by pairing, filtering, or aggregating rows — for example "odd-vs-even game matchups", "Player 1 minus Player 2 wins", or sum-of-metric deltas between two cohorts. Covers reading the PDF for column semantics, inspecting the workbook, mapping question terms to columns, vectorised pandas pairing, and writing answer.txt in the exact format the prompt requires.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+ with pandas and openpyxl; a PDF reader (pypdf, PyPDF2, or poppler-utils `pdftotext`); read access to /root/data.xlsx and /root/background.pdf; write access to /root/answer.txt.
---

```yaml
purpose: >
  Solve a financial-modeling-qa task: read /root/background.pdf for
  domain context, inspect /root/data.xlsx to learn its schema, map the
  question's terms (games, matches, players, wins) to actual columns,
  compute a single numeric answer with vectorised pandas, and write
  just that number to /root/answer.txt. The reusable move is "read PDF
  → inspect workbook → pair/aggregate → emit bare value" — the
  question phrasing varies but the workflow does not.

trigger_when:
  - Task instruction names /root/data.xlsx and /root/background.pdf as inputs.
  - Task instruction asks for a single numeric value written to /root/answer.txt.
  - Question phrasing involves pairing or partitioning rows (odd/even, before/after, cohort A vs cohort B) and aggregating an outcome column.
  - Question phrasing contains "the value of X minus Y" or "the number of …".

do_not_use_when:
  - The answer is freeform text, multi-line, or a chart rather than a single value.
  - No /root/background.pdf is supplied — column semantics cannot be assumed without it.
  - The task is to modify the workbook or produce a new spreadsheet rather than answer a question about it.

scope_and_approval: >
  Read-only on /root/data.xlsx and /root/background.pdf. The only write
  is /root/answer.txt, which must contain the bare answer value (no
  labels, no units, no prose) per the instruction's format note.
  Computation runs entirely locally — no network, no external services.

steps:
  - name: read-instruction
    description: >
      Open the task instruction.md. Capture (a) the exact question, (b)
      the answer-format note ("only write the number", "value of X minus
      Y", required precision/sign), and (c) the input paths. Write a
      one-line restatement of the question before touching data.
  - name: read-background
    description: >
      Extract text from /root/background.pdf. The PDF defines what the
      rows mean — what a "game", "match", "trade", or "trial" is, which
      column holds the outcome, what counts as a win, and whether ties
      are excluded. Skipping this step is the #1 failure mode. The
      bundled scripts/inspect_inputs.py dumps the PDF and every sheet
      in one shot.
  - name: inspect-data
    description: >
      Load /root/data.xlsx. Print sheet names, df.shape, df.columns,
      df.dtypes, and df.head() for each sheet. Confirm (1) the row
      identifier column (game/trial number — is it stored or implied by
      row order?), (2) the outcome column(s), (3) whether the workbook
      is 0- or 1-indexed. Use scripts/inspect_inputs.py rather than
      re-writing this boilerplate.
  - name: align-question-to-columns
    description: >
      Map the question vocabulary to confirmed column names. For the
      canonical question, "odd numbered games" = rows where game % 2
      == 1, "Player 1" = those rows, "match k" = pair (game 2k-1, game
      2k), and "won" is decided by the outcome column whose meaning the
      PDF gave you. Write the mapping as a short comment in your script
      so the computation is auditable.
  - name: compute-answer
    description: >
      Implement the computation with vectorised pandas. For pairing
      questions, follow references/pairing-recipes.md — split into odd
      and even subframes, align them, decide the per-match winner from
      the outcome column, then aggregate. Avoid per-row Python loops.
      Keep the sign of the result faithful to the question's direction.
  - name: validate-answer
    description: >
      Sanity-check before writing. Total wins ≤ number of matches (=
      n_rows // 2). The sign of the result is consistent with which
      side the question subtracts. If practical, recompute via an
      independent method (e.g. explicit pairing vs groupby) and confirm
      both agree. Print the breakdown (P1 wins, P2 wins, ties) so the
      reasoning is visible in the trajectory.
  - name: write-answer
    description: >
      Write the bare value to /root/answer.txt with no surrounding
      prose, label, or unit. If the instruction says "only write the
      number", write only digits (with leading "-" for negatives, no
      "+" for positives). End with a single newline. Re-read the file
      to confirm it contains exactly what was intended.

decisions:
  - signal: No PDF reader is installed in the environment.
    action: Try `pip install pypdf` first; if pip is unavailable, fall back to `pdftotext` from poppler-utils (`apt-get install -y poppler-utils`). scripts/inspect_inputs.py already tries both in order.
  - signal: The workbook has more than one sheet.
    action: Print every sheet's schema. Pick the sheet whose columns match the question's vocabulary; if two sheets plausibly match, re-read the background to disambiguate. Never silently default to the first sheet.
  - signal: The game/match identifier is not a stored column.
    action: Assume the rows are already in game order and assign `game = range(1, len(df) + 1)`. Verify by spot-checking that this matches any narrative game numbers referenced in the PDF.
  - signal: The outcome column is a number (score / profit), not a win/loss label.
    action: For each match (pair of rows) the winner is the side with the higher number — unless the background PDF defines a different convention. Ties don't count for either side by default.
  - signal: Two columns plausibly represent the outcome (e.g. score_a and score_b on a single row per match).
    action: Re-read the background to confirm the row granularity. If a single row already represents a match, the odd/even pairing logic doesn't apply — winner is decided directly from the two score columns.
  - signal: Total wins + ties ≠ total matches, or the answer is suspiciously round.
    action: Investigate missing rows, dtype coercion (e.g. "Win " with trailing space), or off-by-one in the pairing. Don't write answer.txt until the discrepancy is explained.
  - signal: The question asks for "(X) minus (Y)" and the natural ordering gives a negative number.
    action: Keep the sign. Never wrap in abs(). The grader expects the signed difference.

modes:
  - name: quick
    body: >
      Single-pass workflow for confident agents: run
      scripts/inspect_inputs.py, sketch the mapping in a comment, write
      one pandas script that computes and writes the answer. Suitable
      when the workbook schema is unambiguous after one inspection.
  - name: careful
    body: >
      Two-pass workflow when the schema or outcome semantics are
      unclear. First pass: inspect inputs and write the
      question→columns mapping as a markdown note. Second pass:
      implement the computation, compute the answer via two independent
      methods, and only write to answer.txt if both agree.

scenarios:
  - need: Odd-vs-even player matchup, signed win-count difference (the canonical task).
    context: >
      data.xlsx has one row per game with a game-number column and an
      outcome column. The background PDF defines a match as one
      odd-numbered game played by Player 1 against the next
      even-numbered game played by Player 2, with the winner of the
      match being whichever player's game had the better outcome.
    action: >
      Run scripts/inspect_inputs.py. Confirm the game-number and
      outcome columns. Apply Recipe 1 from references/pairing-recipes.md
      to build the matches frame. Apply Recipe 2 or 3 (label vs
      higher-score) depending on the outcome shape. Write
      `p1_wins - p2_wins` to /root/answer.txt as a plain signed
      integer.
    outcome: >
      A single integer (possibly negative) in answer.txt and a printed
      breakdown of P1 wins, P2 wins, and ties in the trajectory.
  - need: Net-metric difference between two cohorts of trades.
    context: >
      Same input shape but the question is "sum of Player 1 P&L minus
      sum of Player 2 P&L".
    action: >
      Same pairing scaffolding. Swap the per-match winner comparison
      for Recipe 4 (sum-of-metric). Cast to int only if the background
      guarantees integer values.
    outcome: A signed scalar (int or float as appropriate) in answer.txt.

anti_patterns:
  - Writing a computation before reading background.pdf — column meanings are not derivable from the spreadsheet alone.
  - Hardcoding column names like "game_number" or "result" instead of inspecting df.columns and matching what's actually there.
  - Assuming "game 1" is the first row without verifying — workbooks frequently 1-index in a stored column while pandas is 0-indexed.
  - Iterating row-by-row in Python when a vectorised pandas pairing is one expression.
  - Writing prose, units, or labels to answer.txt when the instruction says "only write the number" — emit just the number.
  - Wrapping the result in abs() when the question explicitly asks for X minus Y. Negative answers stay negative.
  - Silently defaulting to the first sheet when the workbook has multiple sheets — confirm which sheet answers the question first.
  - Using the absolute value or count of all rows where a flag is set, instead of the per-match comparison the question actually asks for.
```
