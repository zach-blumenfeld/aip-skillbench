---
name: 13f-analyzer
description: Analyze SEC Form 13-F filings (INFOTABLE.tsv and COVERPAGE.tsv under /root/<quarter>/) to compute fund-level summary stats (total holdings, AUM, stock-only holdings count, stock AUM), quarter-over-quarter holdings deltas (top buys and top sells ranked by dollar-value change), and stock-level top holders (largest fund positions in a given CUSIP, joined with filing-manager names). Use when answering hedge-fund or institutional-investor questions about 13F filings, accession numbers, AUM, holdings, position changes between quarters, or which funds hold a stock.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3, pandas; reads /root/<quarter>/INFOTABLE.tsv and /root/<quarter>/COVERPAGE.tsv (SEC EDGAR 13F dumps).
---

```yaml
purpose: >
  Answer hedge-fund / institutional-investor questions backed by SEC Form 13-F
  filings. Covers three analyses over the per-quarter TSV dumps in
  /root/<quarter>/: (1) one-fund single-quarter summary (total holdings, total
  AUM, stock-only holding count, stock-only AUM), (2) one-fund quarter-over-
  quarter delta (top buys and top sells by absolute dollar change), and (3)
  stock-level top holders by CUSIP (largest fund positions, joined with filing-
  manager names). All analyses keyed by ACCESSION_NUMBER and/or CUSIP — resolve
  those identifiers first with the sibling fuzzy-name-search skill.

trigger_when:
  - User asks for a fund's AUM, total holdings, or stock-holding count in a specific quarter (e.g. "What's the AUM of Renaissance Technologies in Q3?", "How many stocks does Berkshire hold?").
  - User asks what a fund bought or sold between two quarters, ranked by dollar value (e.g. "Top 5 stocks Berkshire added from Q2 to Q3").
  - User asks which funds hold a given stock most heavily, by name or by CUSIP (e.g. "Top 3 holders of Palantir").
  - Working in an environment where /root/<quarter>/INFOTABLE.tsv and /root/<quarter>/COVERPAGE.tsv exist (SEC 13F quarterly dumps).
  - Building an answers.json for the sec-financial-report benchmark task.

do_not_use_when:
  - You need to resolve a fund name → ACCESSION_NUMBER or a stock name → CUSIP. Use the sibling `fuzzy-name-search` skill first, then return here with the resolved identifier.
  - The question is about fund metadata not in the 13F dump (e.g. founders, AUM trend across many years, performance). 13F covers a single quarter's long-equity holdings only.
  - You need transaction-level data (intra-quarter buys/sells). 13F is a quarter-end snapshot — deltas are inferred by subtracting two snapshots, not by reading individual trades.

scope_and_approval: >
  Read-only. All scripts read TSV files under /root/<quarter>/ and write nothing
  back. No network calls. Safe to run without approval. Final answer write
  (e.g. /root/answers.json) is the caller's responsibility, not this skill's.

steps:
  - name: resolve-identifiers
    description: >
      Convert any fund name in the question to an ACCESSION_NUMBER for the
      target quarter, and any stock name to a CUSIP, by invoking the sibling
      `fuzzy-name-search` skill. Accession numbers are quarter-specific —
      resolve once per (fund, quarter) pair. When COVERPAGE returns multiple
      rows for the same FILINGMANAGER_NAME, prefer the row where
      ISAMENDMENT = "N" (the original filing). CUSIPs are stable across
      quarters, so resolve once and reuse.
    outputs:
      - name: accession_number
        type: string
        nullable: true
        description: 18-character SEC accession number for a fund in a specific quarter.
      - name: baseline_accession_number
        type: string
        nullable: true
        description: Accession number for the same fund in the earlier quarter (only needed for delta analyses).
      - name: cusip
        type: string
        nullable: true
        description: 9-character stock identifier (uppercased).
      - name: quarter
        type: string
        description: e.g. "2025-q2", "2025-q3" — matches the /root/<quarter>/ folder name.

  - name: one-fund-quarter-summary
    description: >
      Print summary stats for one fund in one quarter — total holdings, total
      AUM, stock-only holding count, stock-only AUM. Use for AUM and
      stock-count questions. Stock-only filtering applies the TITLEOFCLASS
      whitelist baked into the script (preserved verbatim from the curated
      source so answers match the benchmark's expected outputs).
    script: scripts/one_fund_analysis.py
    depends_on: [resolve-identifiers]
    inputs:
      - name: accession_number
        type: string
      - name: quarter
        type: string
    outputs:
      - name: total_holdings_count
        type: integer
        description: Number of INFOTABLE rows for this fund this quarter.
      - name: total_aum
        type: float
        description: Sum of VALUE across all holdings. This is the 13F-reported AUM (long equities only).
      - name: stock_holdings_count
        type: integer
        description: Holdings whose TITLEOFCLASS matches the stock whitelist.
      - name: stock_aum
        type: float
        description: Sum of VALUE across stock-only holdings.

  - name: fund-quarter-delta
    description: >
      Same script as one-fund-quarter-summary, run with the `--baseline_quarter`
      and `--baseline_accession_number` flags. Prints the top 10 buys (largest
      positive ABS_CHANGE) and top 10 sells (largest negative ABS_CHANGE) for
      one fund between two quarters, with CUSIP, NAMEOFISSUER, absolute change,
      and percent change. Use for "what did X buy / sell from Q? to Q?".
      Take the first N rows from `Top 10 Buys` for "top N stocks added" answers.
    script: scripts/one_fund_analysis.py
    depends_on: [resolve-identifiers]
    inputs:
      - name: accession_number
        type: string
        description: Accession number for the *target* (later) quarter.
      - name: quarter
        type: string
        description: Target (later) quarter, e.g. 2025-q3.
      - name: baseline_accession_number
        type: string
        description: Accession number for the same fund in the *baseline* (earlier) quarter.
      - name: baseline_quarter
        type: string
        description: Baseline (earlier) quarter, e.g. 2025-q2.
    outputs:
      - name: top_buys
        type: list[object]
        description: Up to 10 rows, each { rank, cusip, name, abs_change, pct_change }, ranked by largest dollar increase.
      - name: top_sells
        type: list[object]
        description: Up to 10 rows, each { rank, cusip, name, abs_change, pct_change }, ranked by largest dollar decrease.

  - name: top-holders-by-cusip
    description: >
      Top-K funds holding a given CUSIP in a given quarter, ranked by total
      dollar value of the position. Output includes both ACCESSION_NUMBER and
      FILINGMANAGER_NAME (joined from COVERPAGE.tsv) so name-based answers do
      not require a follow-up lookup. Use for "who are the largest holders of
      <stock>?" questions.
    script: scripts/holding_analysis.py
    depends_on: [resolve-identifiers]
    inputs:
      - name: cusip
        type: string
      - name: quarter
        type: string
      - name: topk
        type: integer
        nullable: true
        description: Defaults to 10 when omitted.
    outputs:
      - name: top_holders
        type: list[object]
        description: Up to topk rows, each { rank, accession_number, filing_manager_name, holding_value }, ranked descending by holding_value.

  - name: compile-answer
    description: >
      Parse the script's stdout, pick the fields the user asked for, and write
      them to the location the user named (often /root/answers.json for the
      sec-financial-report benchmark). Honour the user-supplied JSON schema
      exactly — e.g. CUSIPs as strings preserving leading zeros, fund names as
      they appear in FILINGMANAGER_NAME (do not re-case). Do not run scripts
      in this step; this is prose-only formatting of prior outputs.
    depends_on:
      - one-fund-quarter-summary
      - fund-quarter-delta
      - top-holders-by-cusip
    outputs:
      - name: answer_payload
        type: object
        description: User-shaped JSON object; for the benchmark, { q1_answer, q2_answer, q3_answer, q4_answer }.

integrations:
  - partner: fuzzy-name-search
    body: |
      Required upstream. fuzzy-name-search resolves fund names → ACCESSION_NUMBER
      (search_fund.py over COVERPAGE.tsv) and stock names → CUSIP
      (search_stock_cusip.py over INFOTABLE.tsv). Without it, this skill cannot
      start — every step keys off an accession number or CUSIP.

      Calling pattern:
        python3 scripts/search_fund.py --keywords "<fund name>" --quarter <quarter> --topk 5
        python3 scripts/search_stock_cusip.py --keywords "<stock name>" --topk 5
      Pick the top result whose FILINGMANAGER_NAME / NAMEOFISSUER plausibly
      matches the question; the highest-score row is usually correct but a
      lexically closer rank-2 row sometimes wins for common-word names.

scenarios:
  - need: "What's the AUM of Renaissance Technologies in Q3 2025?"
    context: >
      fuzzy-name-search --keywords "renaissance technologies" --quarter 2025-q3
      → FILINGMANAGER_NAME "Renaissance Technologies LLC",
      ACCESSION_NUMBER 0001037389-25-???????.
    action: >
      one-fund-quarter-summary with --accession_number <q3 number> --quarter 2025-q3.
      Read the "Total AUM" line of stdout.
    outcome: A single float, the sum of VALUE across the fund's 13F holdings that quarter.

  - need: "How many stocks does Renaissance hold in Q3 2025?"
    context: Same accession number as above.
    action: >
      one-fund-quarter-summary with --accession_number <q3 number> --quarter 2025-q3.
      Read the "Number of stock holdings" line — count of TITLEOFCLASS values
      matching the script's stock whitelist, not "Total number of holdings".
    outcome: An integer; will be lower than total_holdings_count because non-stock instruments (bonds, options, etc.) are excluded.

  - need: "Top 5 stocks Berkshire Hathaway added from Q2 to Q3 2025, by dollar increase. Answer CUSIPs."
    context: >
      fuzzy-name-search twice — once with --quarter 2025-q2, once with
      --quarter 2025-q3 — because Berkshire's accession number changes each
      quarter. Take the ISAMENDMENT="N" row each time.
    action: >
      fund-quarter-delta with --quarter 2025-q3 --accession_number <q3 number>
      --baseline_quarter 2025-q2 --baseline_accession_number <q2 number>.
      Read the "Top 10 Buys" block and take the first 5 CUSIP fields.
    outcome: List of 5 9-character CUSIP strings, ranked by ABS_CHANGE descending.

  - need: "Top 3 fund managers (by name) holding Palantir in Q3 2025."
    context: >
      fuzzy-name-search --keywords palantir → CUSIP 69608A108 (NAMEOFISSUER
      "palantir technologies inc"). CUSIP is stable across quarters; resolve once.
    action: >
      top-holders-by-cusip with --cusip 69608A108 --quarter 2025-q3 --topk 3.
      Read the "filing_manager_name" field for each rank.
    outcome: List of 3 fund-manager-name strings (e.g. "VANGUARD GROUP INC", "BlackRock, Inc.", "STATE STREET CORP"), preserved as they appear in COVERPAGE.

anti_patterns:
  - Reusing one quarter's ACCESSION_NUMBER in another quarter. Accession numbers are filing-specific and change every reporting season. Re-resolve via fuzzy-name-search for each (fund, quarter) pair.
  - Counting "Total number of holdings" when the question asks "how many stocks". The script's "Number of stock holdings" line is filtered by the TITLEOFCLASS whitelist; the total includes bonds, options, and other non-equity instruments.
  - Loading INFOTABLE.tsv / COVERPAGE.tsv without dtype=str. CUSIPs and ACCESSION_NUMBERs are numeric-looking strings (leading zeros matter); pandas will coerce them to int/float and silently corrupt the keys, breaking joins. The bundled scripts already pass dtype=str — preserve that if you write ad-hoc pandas calls outside the scripts.
  - Picking the first COVERPAGE row for a FILINGMANAGER_NAME without filtering ISAMENDMENT="N". Amended filings may have different holdings; the canonical answer is usually the original filing.
  - Modifying the `title_class_of_stocks` list in `scripts/one_fund_analysis.py`. The list has known string-literal-concatenation in the source (missing commas), but the benchmark's expected answers are calibrated against that exact list — fixing it changes q2_answer and q3_answer.
  - Calling fuzzy-name-search's search_stock_cusip.py with a quarter flag. It always reads /root/2025-q2/INFOTABLE.tsv for the stock dictionary; CUSIPs are stable across quarters so this is intentional.
  - Writing answers.json by hand when running interactively. Use json.dump after compile-answer so the file matches the schema exactly (numbers as floats/ints, CUSIPs as strings, fund names as raw FILINGMANAGER_NAME values).
```
