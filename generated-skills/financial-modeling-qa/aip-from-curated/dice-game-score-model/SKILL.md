---
name: dice-game-score-model
description: Build the ModelOff 2016 Round 1 Section 3 "Roll The Dice" model and answer analytical questions about the 6,000 simulated turns / 3,000 games in the provided workbook. Computes each turn's score under all six categories (High and Often, Summation, Highs and Lows, Only two numbers, All the numbers, Ordered subset of four), the best turn score, and the best game score (two turns, distinct categories). Use whenever the agent is given a dice-roll simulation workbook plus the background case pack and needs to answer multiple-choice or free-response questions about turn or game scores, their distributions, maxima, counts of qualifying turns, or category usage.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Score every turn in the simulation workbook under all six categories, pick each
  turn's best score and each game's best-pair (distinct-category) score, roll
  those up into a full distribution of per-category hits, score totals, means,
  medians, maxima and category usage, then answer the user's question against
  that computed analysis. The computation is deterministic and the only
  non-deterministic step is writing the final answer.

trigger_when:
  - The agent is handed the Round 1 Section 3 "Roll The Dice" workbook plus the
    accompanying background pack and asked a question about turn or game scores.
  - A dice-roll simulation workbook (one row per turn, six roll columns, grouped
    into two-turn games by game number) needs its per-turn and per-game scores
    computed under the six scoring categories described in the pack.

do_not_use_when:
  - The task asks you to build or modify the Excel workbook itself (add formulas,
    reformat cells, apply color conventions). This skill only reads the workbook
    and reports computed answers; it does not round-trip the file.
  - The workbook describes a different game or a different scoring rubric than
    the six categories listed in `references/scoring-rules.md`.

steps:
  - name: compute
    kind: execution
    description: >
      Load the simulation workbook, compute each turn's score under all six
      categories, pick each turn's best category and score, pair each game's
      two turns under every distinct-category combination to find the best game
      score, and emit the full analysis object (distributions, totals, counts,
      category usage, top games) that downstream steps read from.
    inputs:
      - name: data_file
        type: string
        description: Absolute path to the simulation .xlsx workbook (in the task container this is typically /root/data.xlsx).
      - name: question
        type: string
        description: The user's question, verbatim. Pass "" (empty string) if no specific question was asked and you want the full analysis.
    script: scripts/compute_analysis.py
    inputs_to: answer

  - name: answer
    kind: client_task
    description: >
      Write the final answer to the user's question using only figures from the
      computed analysis. If the question is multiple-choice, state the chosen
      option and the figure it matches. If no question was supplied, deliver a
      brief tour of the key figures.
    inputs:
      - name: data_file
        type: string
      - name: question
        type: string
      - name: analysis
        type: object
        description: The full analysis object produced by the compute step; the keys are described in references/scoring-rules.md and the answer template.
    template: assets/answer_template.md
    references:
      - path: references/scoring-rules.md
        description: Load whenever the question references a scoring category by name, when the answer depends on a category's exact criteria, or when sanity-checking a surprising figure.
    inputs_to: end

  - name: end
    kind: end
    description: The user's question plus the final answer, with the full analysis object retained for traceability.
    inputs:
      - name: data_file
        type: string
      - name: question
        type: string
      - name: analysis
        type: object
      - name: answer
        type: string

anti_patterns:
  - Re-deriving a figure (mean, max, category count) in prose when the compute
    step already placed it in the analysis object.
  - Picking a game's best score by taking each turn's best category independently
    and summing them; the two turns must use **different** categories, and the
    compute step already enforces that.
  - Letting a fixed-value category (`only_two_numbers`, `all_the_numbers`,
    `ordered_subset_of_four`) count as a "hit" when the criteria are not met —
    those categories score 0 on turns that do not qualify.
  - Treating "ordered subset of four" as any ordered run of four consecutive
    integers from the full faces; it only awards when four adjacent rolls in
    the recorded order step by exactly +1 or exactly −1.
  - Replacing the computed answer with a guess when the workbook layout is
    unfamiliar; if the compute step fails, surface the error rather than
    inventing figures.
```
