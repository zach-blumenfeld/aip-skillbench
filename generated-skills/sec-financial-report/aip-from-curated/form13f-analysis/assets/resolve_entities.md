Pick the exact filings and securities to analyze, then write the analysis plan.

Request:
{question}

Fund search results (per query: ranked manager-name matches; each match lists every filing that
manager made in that quarter folder, plus `suggested_accession_number`):
{fund_candidates}

Stock search results (per query: ranked issuer-name matches with CUSIP, class title, number of
INFOTABLE rows and total reported value excluding option rows):
{stock_candidates}

Search errors:
{search_errors}

Resolve each entity:

1. Fund: choose the manager the user means. Ties in score are common (similar names); equal scores
   are already ordered holdings filers first, largest `holdings_value` first, but decide by the user's
   wording and city/state too (e.g. "berkshire" → Berkshire Hathaway Inc, not its insurance units). Then use that match's
   `suggested_accession_number` — the original (non-amendment) holdings report for the quarter's main
   period. Do not use a `13F NOTICE` filing (it has no holdings) or a late filing for an older period.
   Use an amendment only if the user asks for it. Note blank `is_amendment` means original filing.
2. Stock: choose the CUSIP of the actual common stock — the match with the most `infotable_rows` and
   `total_value_excl_options` among same-name matches; others are options or typos. If the company has several
   share classes and the user did not specify, include each class.
3. If nothing plausible matched, re-run the search yourself with other keywords:
   `python3 scripts/f13lib.py search-fund --keywords "<name>" --quarter <q>` or
   `python3 scripts/f13lib.py search-stock --keywords "<name>" --quarter <q>` (from the skill folder;
   add `--data_root <dir>` if the data is not under /root). Matches list only filings for the
   quarter's main period; `other_period_filings` counts late filings for older periods.

Produce `analysis_plan` (object) with:
- `fund_summaries`: list of objects with `accession_number`, `quarter` — holdings count, AUM, stock
  holdings/AUM, top positions of one fund in one quarter.
- `comparisons`: list of objects with `accession_number`, `quarter` (the later quarter),
  `baseline_accession_number`, `baseline_quarter` (the earlier quarter), optional `topn` (default 10)
  — top buys/sells, new and exited positions. A comparison already includes both quarters' summaries.
- `top_holders`: list of objects with `cusip`, `quarter`, optional `topk` (default 10; raise it if
  the user asks for more holders) — which funds hold the stock with the highest value.
- `stock_list_mode`: `as_shipped` (default; the source skill's definition of a stock holding) or
  `intended` (adds ADRs, class B, ordinary shares, etc.). Use `intended` only if the user explicitly
  defines stocks to include ADRs or those classes.
Include only the analyses the request needs; use empty lists for the rest. A `data_root` set at
plan-request stays in the state and is used automatically; do not drop it.
