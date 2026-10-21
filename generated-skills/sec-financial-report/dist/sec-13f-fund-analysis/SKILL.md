---
name: sec-13f-fund-analysis
description: Analyze SEC Form 13F bulk data sets (COVERPAGE/INFOTABLE/SUMMARYPAGE .tsv per quarter) to answer hedge-fund questions - fuzzy-find a fund's accession number by manager name, get its AUM and number of stock holdings, compare its holdings between two quarters (top buys/sells by dollar value change), fuzzy-find a stock's CUSIP by name, and rank the managers holding a stock. Use for 13F / institutional holdings / "what did Berkshire buy" / "who holds Palantir" tasks.
compatibility: python3>=3.9 with pandas (tested 2.3.3) and rapidfuzz (tested 3.14.3); no network needed.
---

# SEC 13F Fund Analysis

## Trigger When

1. A task points at SEC Form 13F bulk data folders (e.g. `/root/2025-q2`, `/root/2025-q3` holding `COVERPAGE.tsv`, `INFOTABLE.tsv`, `SUMMARYPAGE.tsv`, `SUBMISSION.tsv`).
2. Asked for a fund's AUM, number of holdings/stocks, or quarter-over-quarter buys/sells (e.g. Renaissance Technologies, Berkshire Hathaway).
3. Asked for a stock's CUSIP from its name, or which fund managers hold a stock the most.
4. Any institutional-holdings / hedge-fund-activity analysis built on 13F filings.

## Purpose

Turns the SEC 13F quarterly bulk TSVs into answers with one script, `scripts/f13.py`: fuzzy fund search that returns the accession number of the right filing, fund summaries (AUM, stock count), quarter-to-quarter holding changes, CUSIP lookup by issuer name, and top holders of a CUSIP. It carries the 13F data traps an agent would otherwise fall into: blank amendment flags, NOTICE filings with no holdings, late filings for older periods, amendments that duplicate holdings, typo CUSIPs, and the title-of-class rule that defines a "stock".

## Setup

1. Check the runtime before the first script: `python3 -c "import pandas, rapidfuzz"`. If either is missing, name it, then run `pip3 install --break-system-packages pandas rapidfuzz`.
2. Find the quarter folders: `ls /root`. Each quarter folder (`2025-q2`, `2025-q3`, ...) must contain the TSVs. `--quarter` is the folder name. If the data lives somewhere other than `/root/<quarter>/`, pass `--data_root <dir>` **before** the subcommand.
3. Run every command from this skill's folder as `python3 scripts/f13.py [--data_root DIR] <subcommand> ...`. Each call reads a ~340 MB INFOTABLE and takes about 5–25 s, so don't loop over many calls when one will do.

## Workflow

Progress:
- [ ] 1. Classify each question (decision `question_kind`)
- [ ] 2. Resolve funds to accession numbers (script `search-fund` + decision `is_intended_fund`)
- [ ] 3. Resolve stocks to CUSIPs (script `search-stock` + decision `is_intended_stock`)
- [ ] 4. Run the analysis (script `fund`, `compare` or `holders`)
- [ ] 5. Write the answer file (client task)

### 1. Decision: `question_kind`

Answer this for each question in the task:

```yaml
question_kind:
  type: choice
  instructions: What does the question ask for?
  criteria:
    fund_summary: One fund in one quarter - AUM, total holdings, number of stocks held.
    quarter_change: One fund across two quarters - increased/decreased/new/exited positions, top buys or sells.
    top_holders: Which managers/funds hold a given stock the most in a quarter.
    stock_lookup: Only the CUSIP (or identity) of a stock.
    other: None of the above; compose from the subcommands below or the TSVs directly.
```

Steps 2–4 then follow. `fund_summary` and `quarter_change` need step 2. `top_holders` and `stock_lookup` need step 3.

### 2. Resolve a fund to its accession number (script + decision)

Accession numbers change every filing, so search **each quarter separately**:

```bash
python3 scripts/f13.py search-fund --quarter 2025-q3 --keywords "renaissance technologies" --topk 10
python3 scripts/f13.py search-fund --quarter 2025-q3 --accession_number 0001037389-25-000064   # exact lookup / verify
```

Each result shows ACCESSION_NUMBER, FILINGMANAGER_NAME, period, REPORTTYPE, address, Form 13F file number, SUMMARYPAGE entry count and value, and flags:
- `EFFECTIVE`: this filing holds (part of) the filer's holdings for the folder's main period. Use these.
- `NOTICE-NO-HOLDINGS`: a 13F NOTICE. Holdings are reported by another manager, so never analyze it.
- `OTHER-PERIOD`: a late filing or amendment for an older quarter. Don't use it for this quarter.
- `AMENDMENT:<type>`: an amendment filing.

Go down the ranked list and answer for each candidate until one is true:

```yaml
is_intended_fund:
  type: noul
  instructions: Is this filing the investment manager the question names (using any hint such as founder, e.g. "founded by Jim Simons", "Warren Buffett's"), filed as a holdings report for this quarter?
  criteria:
    true: The FILINGMANAGER_NAME is that firm's main 13F filer (e.g. "RENAISSANCE TECHNOLOGIES LLC", "Berkshire Hathaway Inc"), the result is flagged EFFECTIVE, and it is not a NOTICE.
    false: A subsidiary or affiliate (e.g. "Berkshire Hathaway Homestate Insurance Co."), a different firm sharing a word ("Renaissance Investment Holdings Ltd.", "Berkshire Asset Management"), a NOTICE, or an OTHER-PERIOD filing.
```

A false positive silently answers about the wrong fund, so reconsider any close call that leans true. If no candidate in the top 10 is true, retry with a shorter or alternate name (drop "LLC", "Inc", "Management") or `--topk 30`. When the same filer (same CIK) has more than one `EFFECTIVE` accession for the quarter (original plus a small NEW HOLDINGS amendment), pass them all comma-separated in step 4.

### 3. Resolve a stock to its CUSIP (script + decision)

```bash
python3 scripts/f13.py search-stock --quarter 2025-q3 --keywords palantir --topk 10
```

Results are unique CUSIPs ranked by match score, then by how many filings hold them. The last line is `BEST_CUSIP: ...`. Typo CUSIPs (e.g. `69608A109` held by 1 filing vs. the real `69608A108` held by 2,821) sink to the bottom.

```yaml
is_intended_stock:
  type: noul
  instructions: Is the BEST_CUSIP row the company the question names, as its common/ordinary shares?
  criteria:
    true: The issuer name is that company and the CUSIP is held by many filings (the real CUSIP has by far the most).
    false: A different company with a similar name (e.g. "palatin technologies" for Palantir), or a rarely held variant CUSIP.
```

If false, take the highest-ranked row that is the intended company. If no row matches, rerun with `--all_classes`, which searches every non-option security, not just the stock title classes (e.g. issuers filed as "SHS", "ORD", "ADS"). For a specific share class (Alphabet A vs C), choose by the class the question names.

### 4. Run the analysis (scripts)

**fund_summary**

```bash
python3 scripts/f13.py fund --quarter 2025-q3 --accession_number 0001037389-25-000064
```

| Question asks for | Use the output line |
|---|---|
| AUM / assets / portfolio value | `Total AUM (sum of VALUE, US dollars)`. It should equal the `SUMMARYPAGE TABLEVALUETOTAL cross-check`. |
| Number of stocks held | `Number of distinct stocks (CUSIPs)` |
| Number of holdings / positions (all securities) | `Total number of holdings (all rows)` |
| Value held in stocks | `Total stock AUM` |

**quarter_change** (current quarter vs. baseline, each with its own accession):

```bash
python3 scripts/f13.py compare --quarter 2025-q3 --accession_number <Q3 accession> \
    --baseline_quarter 2025-q2 --baseline_accession_number <Q2 accession> --topk 10
```

It prints both summaries, then the top buys (largest dollar VALUE increase, positions opened marked `NEW`) and the top sells (largest decrease, `EXITED` when sold out). It ends with `TOP_BUY_CUSIPS` / `TOP_SELL_CUSIPS` lists in rank order. "Increased investment ranked by dollar value increase" means the top-N of `TOP_BUY_CUSIPS`. Use `--topk` ≥ the N asked. If the question asks about shares bought rather than value, rank by the `share change` column instead.

**top_holders**

```bash
python3 scripts/f13.py holders --quarter 2025-q3 --cusip 69608A108 --topk 10
```

It ranks managers (one per filer CIK, with amendments resolved, main period only) by holding value and ends with `TOP_MANAGER_NAMES`. Answer with the names exactly as filed (`FILINGMANAGER_NAME`). Put/call option rows are excluded by default because "invested in / share value" means shares held. Add `--include_options` only if the question explicitly counts options or notional exposure.

**stock_lookup**: answer with the CUSIP from step 3.

### 5. Client task: write the answer file

Write the answers in the exact schema the task gives: numbers as JSON numbers (not strings, no commas or `$`), CUSIPs as strings in rank order, and fund names as strings in rank order. For example, a task asking for `/root/answers.json`:

```json
{
    "q1_answer": 123456789012,
    "q2_answer": 1234,
    "q3_answer": ["CUSIP1", "CUSIP2", "CUSIP3", "CUSIP4", "CUSIP5"],
    "q4_answer": ["FUND NAME 1", "FUND NAME 2", "FUND NAME 3"]
}
```

Validate it with `python3 -c "import json; print(json.load(open('/root/answers.json')))"` and confirm that each list length matches what was asked.

## Gotchas

- **VALUE is in US dollars** (whole dollars since the 2023 rule change), not thousands. Don't multiply by 1,000. AUM here means total reported 13F value (all rows, including options and non-stock rows).
- **Blank `ISAMENDMENT` means an original filing.** About half of all filings, Renaissance Technologies' among them, leave it blank. A filter like `ISAMENDMENT == "N"` silently drops them. The script handles this.
- **A "stock" is a row whose lower-cased `TITLEOFCLASS` is in the stock-class list** (`com`, `common stock`, `cl a`, `cl b`, `cap stk cl a`, `sponsored adr`, `ord shs`, `shs cl a`, … in `STOCK_TITLE_CLASSES` in `scripts/f13.py`), and that is not a put/call option. Count stocks by distinct CUSIP: a manager such as Berkshire lists one stock on many rows (98 stock rows but 35 distinct stocks in Q3 2025).
- **Search each quarter for its own accession number.** Berkshire Hathaway Inc is `0000950123-25-008343` in 2025-q2 but `0001193125-25-282901` in 2025-q3. Using one quarter's accession in the other finds no rows.
- **Fuzzy-score ties are common** (several "Berkshire Hathaway …" names all score 90–95). Read names and flags; never take rank 1 blindly.
- **Amendments.** A RESTATEMENT replaces the filer's earlier filing. A NEW HOLDINGS amendment adds to it, except that filers often mislabel full re-filings as NEW HOLDINGS (JPMorgan Q3 2025 re-filed all 32,847 rows). `holders` therefore treats a NEW HOLDINGS amendment with at least half the current entry count as a restatement, so nothing is double-counted.
- **Late filings.** Each quarter folder also contains filings for older periods. The script uses the folder's most common `REPORTCALENDARORQUARTER` as the main period, and `holders` counts only that period.
- Value changes include price moves: a fund that bought no shares still shows a dollar "increase" when the stock rose. That is what "ranked by dollar value increase" asks for.
