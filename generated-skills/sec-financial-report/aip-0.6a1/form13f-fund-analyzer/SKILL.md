---
name: form13f-fund-analyzer
description: Analyze SEC Form 13F quarterly data sets (COVERPAGE.tsv, INFOTABLE.tsv) to answer hedge-fund questions — fuzzy-find a fund's accession number by name (e.g. Renaissance Technologies, Berkshire Hathaway) or a stock's CUSIP by company name (e.g. Palantir), then compute the fund's AUM and number of stocks held, its top increased or decreased positions between two quarters ranked by dollar value change, and the top fund managers holding a stock, and write the answers JSON. Use for 13F holdings, AUM, quarter-over-quarter fund activity, and largest-holder questions.
compatibility: Needs python3 (3.10+) with pandas and rapidfuzz; reads SEC Form 13F data set folders (e.g. /root/2025-q2, /root/2025-q3).
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Answer hedge-fund activity questions from the SEC Form 13F quarterly data sets
  (COVERPAGE.tsv + INFOTABLE.tsv per quarter folder): a fund's AUM and number of stocks held,
  the stocks a fund increased most between two quarters ranked by dollar value change, and the
  managers holding the most of a stock. A script fuzzy-searches filer names and issuer names to
  candidate accession numbers and CUSIPs; the agent confirms which candidates the task means; a
  script computes the summaries, quarter-over-quarter changes and top holders; the agent maps
  them onto the task's answer schema and a script writes and checks the answer file.

trigger_when:
  - A task asks for a fund's AUM, number of holdings or stocks, or portfolio changes from SEC 13F filings.
  - A task asks which stocks a manager (e.g. Berkshire Hathaway) bought or increased most between two quarters.
  - A task asks which fund managers hold the most of a stock (by CUSIP or company name) in a quarter.
  - A task hands over SEC Form 13F data set folders (COVERPAGE.tsv, INFOTABLE.tsv, SUMMARYPAGE.tsv) and asks for a fund or stock lookup.

do_not_use_when:
  - The data is not the SEC Form 13F data set layout (e.g. raw EDGAR XML or a broker export); the loaders read COVERPAGE.tsv/INFOTABLE.tsv by column name.
  - The question needs prices, returns or fundamentals that 13F filings do not report.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pandas
    - rapidfuzz

steps:
  - name: search
    kind: execution
    description: Fuzzy-search COVERPAGE filer names per quarter and INFOTABLE issuer names in the current quarter; suggest the best accession number per fund per quarter and the best CUSIP per stock.
    inputs:
      - name: task_statement
        type: string
        description: The task's full question text, verbatim; later steps judge entities and answer formats against it.
      - name: data_root
        type: string
        description: Folder holding one sub-folder per quarter, e.g. /root (container path), so <data_root>/<quarter>/INFOTABLE.tsv exists.
      - name: quarter
        type: string
        description: Folder name of the quarter the questions are about, e.g. 2025-q3.
      - name: baseline_quarter
        type: string
        description: Folder name of the comparison quarter for change questions, e.g. 2025-q2; empty string when no question compares quarters.
      - name: fund_queries
        type: list[*]
        description: One search term per fund the task names, as the task words it (e.g. "renaissance technologies", "berkshire hathaway"), or an accession number (0001172661-25-003151) for an exact lookup; empty list if none.
      - name: stock_queries
        type: list[*]
        description: One company-name search term per stock whose CUSIP must be found (e.g. "palantir"); empty list if none. A stock given by CUSIP needs no search.
      - name: topk
        type: integer
        description: How many ranked rows the task asks for at most (e.g. 5 for a top-5 question); candidates and rankings list at least this many.
      - name: answers_path
        type: string
        description: Where the task wants the answer JSON, e.g. /root/answers.json.
    script: scripts/search.py
    timeout: 900
    outputs:
      - name: fund_candidates
        type: object
        description: "query -> quarter -> {period, candidates: [{name, score, location, form13f_file_number, filings: [{accession_number, report_type, is_amendment, amendment_type, n_holdings, total_value}], best_holdings_filing}], suggested_name, suggested_accession, ambiguous}."
      - name: stock_candidates
        type: object
        description: "query -> {quarter, candidates: [{cusip, name, score, matching_filings, n_filings, matched_share, total_value}], suggested_cusip, suggested_name, ambiguous}."
    inputs_to: select-entities

  - name: select-entities
    kind: client_task
    description: Confirm or correct the suggested accession number per fund per quarter and CUSIP per stock against what the task means.
    inputs:
      - name: task_statement
        type: string
      - name: quarter
        type: string
      - name: baseline_quarter
        type: string
      - name: fund_candidates
        type: object
      - name: stock_candidates
        type: object
    template: assets/select_entities.md
    outputs:
      - name: selection
        type: object
        description: "{\"funds\": {<fund query>: {<quarter folder>: <accession_number>, ...}}, \"stocks\": {<stock query>: <CUSIP>}}. Include the baseline quarter only for funds a change question covers."
      - name: selection_notes
        type: string
        description: One line per entity naming the chosen filer or security and why, especially where the suggestion was overridden or ambiguous.
    inputs_to: analyze

  - name: analyze
    kind: execution
    description: Compute per-filing summaries (AUM, holdings, stock count), quarter-over-quarter changes per CUSIP for funds with two filings, and top holders of each selected CUSIP.
    inputs:
      - name: data_root
        type: string
      - name: quarter
        type: string
      - name: baseline_quarter
        type: string
      - name: selection
        type: object
      - name: topk
        type: integer
    script: scripts/analyze.py
    timeout: 900
    outputs:
      - name: fund_summaries
        type: object
        description: "fund -> quarter -> {accession_number, manager_name, period, total_holdings, aum, distinct_cusips, stock_holdings, stock_value, option_rows, principal_amount_rows, title_list_stock_rows, summarypage_entry_total, summarypage_value_total}."
      - name: holding_changes
        type: object
        description: "fund -> {from, to, basis, top_increases: [{cusip, name, value_base, value, abs_change, pct_change, shares_base, shares, status}], top_decreases, n_new_positions, n_exited_positions, title_list_top_increases}; sorted by abs_change."
      - name: top_holders
        type: object
        description: "stock -> {quarter, cusip, period, n_filers, ranking: [{rank, manager_name, accession_number, value, shares}], ranking_incl_options}."
    inputs_to: compose-answers

  - name: compose-answers
    kind: client_task
    description: Map the computed results onto the answer keys and value types the task's file schema asks for.
    inputs:
      - name: task_statement
        type: string
      - name: selection_notes
        type: string
      - name: fund_summaries
        type: object
      - name: holding_changes
        type: object
      - name: top_holders
        type: object
    template: assets/compose_answers.md
    references:
      - path: references/form13f-data.md
        description: 13F data set columns, value units, amendment and notice semantics, and how each question type maps to a computed field. Load when a question is not covered by the template mapping or a result looks inconsistent.
    outputs:
      - name: answers
        type: object
        description: The answer object exactly as the task's schema shows it (its key names, numbers as JSON numbers, lists of CUSIP or name strings in ranked order).
    inputs_to: write-answers

  - name: write-answers
    kind: execution
    description: Write the answers JSON to the task's path, re-read it, and list type problems (numbers as strings, empty or duplicate entries).
    inputs:
      - name: answers
        type: object
      - name: answers_path
        type: string
    script: scripts/write_answers.py
    outputs:
      - name: answers_written
        type: string
        description: Absolute path of the written answer file.
      - name: answer_warnings
        type: list[*]
        description: Type and shape problems found in the written answers; empty when none.
    inputs_to: answer-check

  - name: answer-check
    kind: decision
    description: Judge whether the written answers match the task's schema exactly.
    inputs:
      - name: task_statement
        type: string
      - name: answers
        type: object
      - name: answer_warnings
        type: list[*]
    questions:
      answers_valid:
        type: noul
        instructions: Does the answer object carry exactly the task's keys, each value of the type the schema shows, with each list as long as the question asks, and no answer_warnings left unexplained?
        criteria:
          true: Every key present and spelled as in the schema, numbers are JSON numbers, list lengths match the question (e.g. 5 CUSIPs, 3 names), no warnings.
          false: A key is missing, renamed or extra, a number is a string, a list has the wrong length, or a warning flags a real problem.
    thresholds:
      answers_valid: 0.2
    inputs_to: route-answers

  - name: route-answers
    kind: router
    description: Valid answers finish; invalid ones get repaired in place.
    branch_on: answers_valid
    branches:
      "true": end
      "false": repair-answers

  - name: repair-answers
    kind: client_task
    description: Fix the answer file in place so it matches the task's schema.
    inputs:
      - name: task_statement
        type: string
      - name: answers
        type: object
      - name: answer_warnings
        type: list[*]
      - name: answers_written
        type: string
    template: assets/repair_answers.md
    outputs:
      - name: repair_notes
        type: string
        description: What was changed in the answer file and why.
    inputs_to: end

  - name: end
    kind: end
    description: The answer file at answers_written holds the final answers (including any repair).
    inputs:
      - name: answers_written
        type: string

anti_patterns:
  - Matching names case-sensitively. Filers spell names in any case ("RENAISSANCE TECHNOLOGIES LLC"); a case-sensitive WRatio ranks unrelated names above the right one. The search script lowercases both sides.
  - Dropping filings whose ISAMENDMENT is blank. Most original filings leave ISAMENDMENT empty rather than "N" (the source search_fund.py required "N" and skipped Renaissance entirely); only "Y" marks an amendment.
  - Taking the first fuzzy match for a fund without checking it filed holdings. Notice filers and affiliates share the famous name; a 13F NOTICE has no INFOTABLE rows.
  - Reusing one quarter's accession number for another quarter; every quarterly filing has its own.
  - Counting stocks or ranking buys with the source's TITLEOFCLASS list. Its missing commas glued half the classes into one string, and TITLEOFCLASS is free text ("shs", "ord", "cap stk cl c") so any list misses real stocks; e.g. it hid Berkshire's new Alphabet class C position. Share positions (SSHPRNAMTTYPE SH, no PUTCALL) are the reliable basis.
  - Summing a manager's original and amendment filings when ranking holders; some "NEW HOLDINGS" amendments repeat the whole table and double the value. Keep each manager's largest filing.
  - Scaling VALUE by 1000. Since 2023 the 13F data sets report VALUE in whole dollars; it matches SUMMARYPAGE TABLEVALUETOTAL.
  - Reading the 340 MB INFOTABLE.tsv whole with all columns; the scripts stream it in chunks with only the needed columns to stay within container memory.
  - Hardcoding accession numbers, CUSIPs or answers from a previous run; every value must come from the files given.
```
