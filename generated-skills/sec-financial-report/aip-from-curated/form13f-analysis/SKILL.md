---
name: form13f-analysis
description: Answer questions about hedge-fund / institutional manager holdings from SEC Form 13F data sets (2025-q2, 2025-q3 under /root) - fuzzy-find a fund by name or accession number and a stock's CUSIP by company name, then compute a fund's number of holdings, AUM, stock holdings and stock AUM, its top buys and sells between two quarters, or the top-k funds holding a stock by value. Use for 13F, 13-F, INFOTABLE, COVERPAGE, AUM, fund holdings, or quarter-over-quarter position changes.
compatibility: Python 3 with pandas and rapidfuzz; expects the SEC 13F TSV data sets unzipped to /root/<quarter>/ (e.g. /root/2025-q2, /root/2025-q3).
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
  Answer questions about institutional managers' holdings from the SEC Form 13F data sets.
  Fund and stock names are resolved by fuzzy search (fund name → accession number per quarter,
  company name → CUSIP), then scripts compute a fund's holdings count, AUM, stock holdings and
  stock AUM, its top buys and sells between two quarters, and the top-k funds holding a stock by
  value. The scripts reproduce the curated 13f-analyzer / fuzzy-name-search definitions exactly and
  fix their data-layout and filing-selection pitfalls.

trigger_when:
  - A question asks about a hedge fund's or asset manager's 13F holdings, AUM, number of holdings, or number of stock holdings in a quarter.
  - A question asks what a fund bought or sold, or how its positions changed, between 2025-q2 and 2025-q3.
  - A question asks which funds hold a given stock the most, by reported value, in a quarter.
  - A fund or stock is named loosely (partial or misspelled name) and its accession number or CUSIP must be found in the 13F data.
  - The SEC 13F TSV data sets (COVERPAGE.tsv, INFOTABLE.tsv) are present under /root/2025-q2 and /root/2025-q3.

do_not_use_when:
  - The question needs live prices, returns, or filings outside the local 13F data sets.
  - The question is about mutual-fund N-PORT, 10-K/10-Q financial statements, or insider Form 4 trades.

steps:
  - name: plan-request
    kind: client_task
    description: List every fund (per quarter) and stock the request names, as search queries.
    inputs:
      - name: question
        type: string
        description: The user's request, verbatim, including any required output file or format.
    template: assets/plan_request.md
    references:
      - path: references/13f-data-guide.md
        description: 13F folder layout, column meanings, metric definitions, and gotchas. Load if the quarter mapping or what a term means in 13F data is unclear.
    inputs_to: search-entities

  - name: search-entities
    kind: execution
    description: Fuzzy-search (rapidfuzz WRatio) fund names in COVERPAGE per quarter and issuer names in INFOTABLE; return ranked candidates with every filing and a suggested accession number.
    inputs:
      - name: fund_queries
        type: list[*]
        description: Objects with keywords (name or accession number) and quarter (2025-q2 / 2025-q3).
      - name: stock_queries
        type: list[*]
        description: Objects with keywords (company name or CUSIP) and quarter.
    script: scripts/search_entities.py
    timeout: 900
    inputs_to: resolve-entities

  - name: resolve-entities
    kind: client_task
    description: Choose the intended fund filing per quarter and the stock CUSIP(s), and write the analysis plan.
    inputs:
      - name: question
        type: string
      - name: fund_candidates
        type: list[*]
        description: Per fund query, ranked manager matches with their filings and suggested_accession_number.
      - name: stock_candidates
        type: list[*]
        description: Per stock query, ranked issuer matches with CUSIP, class, row count, and total value.
      - name: search_errors
        type: list[*]
    template: assets/resolve_entities.md
    references:
      - path: references/13f-data-guide.md
        description: Amendment, notice, late-filing, share-class, and option-CUSIP gotchas. Load when two candidates tie or a fund has several filings.
    inputs_to: run-analyses

  - name: run-analyses
    kind: execution
    description: Compute fund summaries, quarter-over-quarter buy/sell rankings, and top holders of each CUSIP from INFOTABLE.
    inputs:
      - name: analysis_plan
        type: object
        description: fund_summaries, comparisons, top_holders lists and stock_list_mode, as written by resolve-entities.
    script: scripts/run_analyses.py
    assets:
      - assets/stock_title_classes.json
    timeout: 1800
    inputs_to: write-answer

  - name: write-answer
    kind: client_task
    description: Answer every question in the request from the computed results, in the format the request requires.
    inputs:
      - name: question
        type: string
      - name: analysis_plan
        type: object
      - name: results
        type: object
        description: fund_summaries, comparisons, top_holders, errors; values in US dollars.
    template: assets/write_answer.md
    references:
      - path: references/13f-data-guide.md
        description: Exact metric definitions (holdings count, AUM, stock list, buy/sell ranking, top holders). Load if the user's wording does not map cleanly to a result field.
    inputs_to: end

  - name: end
    kind: end
    description: The answer text plus the computed results it was taken from.
    inputs:
      - name: answer
        type: string
      - name: results
        type: object

anti_patterns:
  - Reusing one quarter's accession number on the other quarter's data; every quarter-over-quarter comparison needs the fund searched and resolved in both quarters.
  - Reading INFOTABLE.tsv from /root directly; each quarter's files live in /root/<quarter>/.
  - Dropping filings whose ISAMENDMENT is blank (half of all filings, e.g. Renaissance Technologies in 2025-q3); blank means original filing.
  - Analyzing a 13F NOTICE filing, an amendment, or a late filing for an older period instead of the original holdings report for the quarter.
  - Taking the first fuzzy match when scores tie; choose by the user's wording, location, and size.
  - Treating VALUE as thousands of dollars; since 2023 it is whole dollars.
  - Calling a value change a purchase without noting it is market value (price moves count); check share_change.
  - Quoting pct_change for a new position; the source formula divides by 1 when the baseline is 0.
  - Counting distinct CUSIPs as the number of holdings; holdings are INFOTABLE rows for the filing.
  - Picking an option or typo CUSIP for a stock; the common stock is the same-name match with by far the most rows and value.
  - Hardcoding answers or editing the data; every figure must come from the scripts run on the files present.
```
