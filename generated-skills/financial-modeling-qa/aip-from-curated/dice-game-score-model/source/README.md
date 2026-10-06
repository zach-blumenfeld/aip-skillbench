# source/ — provenance and compile log

This AIP skill was compiled from two curated inputs:

- `source/skills/pdf/` — the curated PDF toolkit skill (SKILL.md, scripts/,
  references/). Used solely for background knowledge of what the pack's PDF
  file is and how to pull text out of it if an agent ever needs to re-read the
  background pack. The compiled skill does **not** actually need to extract
  anything from the PDF to answer a question — the background pack is the
  rules reference, which we have transcribed in `references/scoring-rules.md`.
- `source/skills/xlsx/` — the curated xlsx toolkit skill (SKILL.md, recalc.py,
  LICENSE.txt). Supplies the knowledge of how to read Excel workbooks with
  openpyxl / pandas, which `scripts/compute_analysis.py` applies directly.

The pack's data files are mirrored verbatim under `source/environment/`:
- `background.pdf` — Round 1 Section 3 case pack describing the dice game and
  the six scoring categories.
- `data.xlsx` — 6,000 turns / 3,000 games of simulated dice rolls.
- `Dockerfile` and `MANIFEST.md` — the container the pack is scored in.

## Step-kind choices

- **`compute` → `execution`.** Every piece of logic required — the six category
  score formulas, the "best of six" per turn, the distinct-category pairing per
  game, and every summary statistic — is deterministic and lookup/arithmetic
  over structured inputs. The AIP best-practices guidance makes this an
  unambiguous script step. One file (`scripts/compute_analysis.py`) because the
  pieces are not independently reusable.
- **`answer` → `client_task`.** The final output is a human-readable answer to
  a user question; only the agent can map "which multiple-choice option matches
  <figure>" or write a free-text answer. All numerics come from the analysis
  object in state, so the client step is a mapping-and-writing task, not a
  judgment on the data itself.
- **`end`.** Retains both the final answer and the full analysis so the run
  trace carries the computed figures the answer was drawn from.

No `decision` or `router` step is used: there is no branching logic over the
input — the compute step always runs, the client always writes, and there is
no shortcut path that depends on a classification of the input.

## Line-by-line completeness check vs the source materials

### `source/environment/background.pdf` (case pack)
The pack is a single page of rules. Every rule-bearing sentence is encoded in
the compute script and transcribed in `references/scoring-rules.md`:

- "Each game consists of 2 turns" — enforced in `compute_analysis.py` (fails
  the run if a game number has ≠ 2 turns).
- "For each turn, roll one six-sided die 6 times, making a note of each
  number in the order it was rolled" — the script reads six roll columns in
  index order and preserves order for the ordered-subset-of-four check.
- "no category may be used more than once (i.e. you may not score the two
  hands in the same category)" — enforced by the `if ca == cb: continue`
  guard in `best_game_score`.
- "The workbook provided contains dice rolls from 6,000 simulated turns
  (3,000 games)" — recorded in `references/scoring-rules.md` and surfaced to
  the agent as `analysis.turn_count` / `analysis.game_count`.
- The six scoring rows of the SCORING TURNS table — each is implemented in
  `SCORERS` and documented in the scoring-rules reference.
- "For Questions 20 to 27, select your answer from a multiple choice list.
  For Questions 28 to 29, you are required to type in your answer. When
  finished, please upload your workbook (Question 30)." — surfaced in the
  answer template's guidance ("if the question is multiple-choice, state the
  chosen option **and** the figure it matches"). The workbook-upload meta
  question (Q30) is a **deliberate drop**: this skill answers analytical
  questions against the model and does not round-trip the workbook itself; a
  future `build-workbook` skill is where that belongs.

### `source/skills/pdf/` (curated PDF toolkit)
Deliberate drop in its entirety. The toolkit covers merging, splitting,
rotating, OCR, form filling, watermarking, and encryption — none of which the
dice-game analysis needs. The one piece of PDF knowledge that mattered — that
the background pack's rules exist and what they are — is captured in
`references/scoring-rules.md`. The source copy is preserved under
`source/skills/pdf/` so a reviewer can audit what was pulled.

### `source/skills/xlsx/` (curated xlsx toolkit)
The two pieces this skill actually needs are the openpyxl loading pattern and
the "formulas, not hardcoded values" rule. The loading pattern is applied in
`scripts/compute_analysis.py::load_turns` (uses `openpyxl.load_workbook` with
`data_only=True, read_only=True` so cached values are read without rewriting).
The "use formulas, not hardcoded values" rule and the full formula-error
handling / recalculation workflow (`recalc.py`, LibreOffice setup, error
category table) are **deliberately dropped**: this skill only reads the given
workbook — it never writes one — so recalculation and formula-error scanning
cannot apply. The ModelOff color-coding, number-format, and formula-
construction standards are **deliberately dropped** for the same reason. The
source copy is preserved under `source/skills/xlsx/` so a reviewer can audit
what was pulled.

## Not deliberately dropped — nothing

Every rule, score, criterion, and threshold in the background pack is encoded
in the compute script. The curated-skill drops are category-wide (whole feature
areas not applicable to a read-only analysis), not rule-level.
