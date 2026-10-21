# Source and provenance: sec-13f-fund-analysis

## Provenance

This skill was compiled on 2026-10-20 from two curated Agent Skills. Both are copied verbatim here:

| Source | Files |
|---|---|
| `13f-analyzer/` | `SKILL.md`, `scripts/one_fund_analysis.py`, `scripts/holding_analysis.py` |
| `fuzzy-name-search/` | `SKILL.md`, `scripts/search_fund.py`, `scripts/search_stock_cusip.py` |

The target task statement asks for a hedge-fund Q2 vs. Q3 2025 analysis over the SEC 13F bulk data sets at `/root/2025-q2` and `/root/2025-q3`, with the answers written to `/root/answers.json`. The container is Ubuntu 24.04 with python3, pandas 2.3.3 and rapidfuzz 3.14.3. All four source scripts were functionally tested against the real data sets (`13f-2025-q2.zip` and `13f-2025-q3.zip`, unpacked as in the Dockerfile).

Intent: chain the two sources into one workflow. Fuzzy-search a fund or stock to get an accession number or CUSIP, then analyze: fund summary, quarter-to-quarter change, or top holders of a stock.

## Component kinds

| Component | Kind | Why |
|---|---|---|
| `search-fund` (from `search_fund.py`) | execution | Fuzzy matching, the amendment, period and notice flags, and tie-break ordering are deterministic code over COVERPAGE, SUBMISSION and SUMMARYPAGE. |
| `is_intended_fund` | decision (noul) | Telling the named firm apart from its affiliates or same-word firms ("Berkshire Hathaway Homestate Insurance", "Renaissance Investment Holdings") needs judgment over a written-down yes/no boundary. |
| `search-stock` (from `search_stock_cusip.py`) | execution | Matching, de-duplication by CUSIP and ranking by filer count are deterministic. |
| `is_intended_stock` | decision (noul) | Same-name or look-alike issuers ("palatin" vs. "palantir") need judgment. |
| `question_kind` | decision (choice) | Mapping free-text questions onto the fixed set of analyses. |
| `fund` / `compare` (from `one_fund_analysis.py`) | execution | Sums, stock-class filter, outer merge and ranking are numeric code. |
| `holders` (from `holding_analysis.py`) | execution | Group-by and ranking, amendment resolution and name mapping are deterministic. |
| Output-line lookup table (which printed figure answers "AUM" / "number of stocks") | body table | A small fixed lookup over the script's labeled output. The script prints every figure, and the table removes the ambiguity. |
| Write `answers.json` | client_task | The agent must assemble its answers into the schema the task gives. Only the agent knows that schema and the question order. |

All four source scripts are merged into one `scripts/f13.py` with subcommands, because they share loaders, the stock-class list and the data root.

## Deliberate changes to source behavior (bugs found in functional testing)

1. **`search_fund.py` filtered `ISAMENDMENT == "N"`.** In the real data, 5,192 of 10,799 Q2 filings and 4,957 of 10,422 Q3 filings have a blank ISAMENDMENT, including RENAISSANCE TECHNOLOGIES LLC. The source search therefore silently skipped the best match (verified: it printed Ranks 2–5 only). The new script treats blank as "not an amendment" and flags amendments instead of hiding them.
2. **`search_fund.py` matched case-sensitively** (WRatio without a processor), which hurt matching against upper-case names. The new script uses `rapidfuzz.utils.default_process`.
3. **Fund tie-breaks.** "berkshire hathaway" scores the same against Berkshire Hathaway Inc and two insurance subsidiaries that file 13F NOTICEs. The new script ranks EFFECTIVE holdings filings first, then by portfolio value. It also prints REPORTTYPE, period, flags and SUMMARYPAGE totals, so the `is_intended_fund` decision has the evidence it needs.
4. **`title_class_of_stocks` lost 16 entries to missing commas.** Python concatenated `"sponsored adr" "sponsored ads" "adr" ... "foreign stock" "shs cl a"` into one string, so classes such as `cap stk cl a`, `cl b`, `shs cl a`, `ord shs`, `sponsored adr` and `adr` were never counted as stock. The new script uses the list as written, with each class intended. Impact on the real data: Renaissance Q3 stock rows go from 2,451 to 2,710, and Berkshire's largest Q3 increase, Alphabet (`02079K305`, CAP STK CL A, +$4.34B, a new position), was missing from the source's top buys. This is a deliberate change of results.
5. **`holding_analysis.py` read `/root/INFOTABLE.tsv`** without the quarter folder, so it crashed with FileNotFoundError. It also printed accession numbers only, and it counted a filer twice when the filer submitted an original plus a duplicate amendment (JPMorgan Q3: two accessions with the same 32,847 rows). It also mixed in late filings for older periods. The new `holders` subcommand reads `<root>/<quarter>/INFOTABLE.tsv`, keeps the main period, resolves amendments per CIK, maps each filer to FILINGMANAGER_NAME and upper-cases CUSIPs.
6. **`holders` excludes put/call option rows by default** (the source included them). "Invested … in terms of share value" means shares. `--include_options` restores the source behavior. On the real data the top 3 for Palantir are the same either way.
7. **The stock count is the number of distinct CUSIPs.** The source counted rows, and Berkshire lists one stock on many rows (98 rows vs. 35 stocks). The script prints both figures and the body says which one answers "number of stocks".
8. **`search_stock_cusip.py` was hardcoded to `2025-q2`** and printed the same CUSIP several times (one per duplicate name), plus look-alikes such as "ir" and the typo CUSIP `69608A109`. The new script takes `--quarter`, de-duplicates by CUSIP, ranks by score, then by number of filings holding the CUSIP, and adds `--all_classes` for issuers outside the stock class list.
9. **`PCT_CHANGE` for a new position divided by 1** (the source's zero guard), which printed figures like 433839712100%. The script now prints "n/a (new position)". The `ABS_CHANGE` ranking is unchanged.
10. **`--data_root`** was hardcoded as `/root`. It is now a flag with `/root` as the default.

## Completeness check (source → skill)

| Source item | Where it lives in the skill |
|---|---|
| 13f-analyzer: one-fund summary (holdings count, AUM, stock count, stock AUM) | `fund` subcommand and the Step 4 lookup table |
| 13f-analyzer: two-quarter change, buys and sells ranked by notional value | `compare` subcommand and Step 4 |
| 13f-analyzer: top funds holding a stock (`--topk 10`) | `holders` subcommand and Step 4 |
| one_fund_analysis: stock filter by TITLEOFCLASS list, groupby CUSIP (first name/class, sum VALUE) | `STOCK_TITLE_CLASSES`, `fund_summary()`, Gotchas |
| one_fund_analysis: exit 1 with "ERROR: No data found" when no stock rows | `fund_summary()` (also when the accession has no rows at all) |
| one_fund_analysis: outer merge, fillna 0, ABS_CHANGE, PCT_CHANGE with zero guard, top 10 buys and sells | `cmd_compare()` (the top-N is now `--topk`, default 10) |
| holding_analysis: group by accession, sum VALUE, sort desc, head(topk) | `cmd_holders()` (grouped per CIK so amendments merge) |
| fuzzy-name-search: Levenshtein-based fuzzy search, inaccurate names OK | `search-fund` / `search-stock` (rapidfuzz WRatio) |
| search_fund: `--keywords`, `--quarter`, `--topk 10`, prints ACCESSION_NUMBER, period, name, street, city, state, file number | `print_filing()` |
| search_fund: exact search by `--accession_number`, score 100, "No fund found …" message | `cmd_search_fund()` |
| search_fund: skip amendments | Replaced by flags and EFFECTIVE ranking (change 1) |
| search_stock_cusip: stock-class filter, upper-case CUSIP, de-dup, lower-case names, WRatio, prints Name and CUSIP | `cmd_search_stock()` |
| Example outputs in fuzzy-name-search SKILL.md (Bridgewater ranks, Palantir 69608A108) | Deliberate drop: illustrative only. The skill shows its own commands and output description instead. |
| Note "accession numbers will change in reporting seasons" (task statement) | Gotchas and Step 2 |

### Deliberate drops

- **Bridgewater example output blocks** (fuzzy-name-search SKILL.md): sample output for one fund that the task doesn't use. The output format is described in Step 2.
- **Docstrings that mention a `coverpage` argument or a `limit` parameter that don't exist** (search_stock_cusip.py, search_fund.py): stale documentation with no behavior.
- **`matched_cover.empty` check after `.iloc[0]`** in search_stock_cusip.py: dead code (it can never be empty after `.iloc[0]`).
