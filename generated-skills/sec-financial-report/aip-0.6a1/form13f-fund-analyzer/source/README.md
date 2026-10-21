# form13f-fund-analyzer — source and compilation notes

## Provenance

Compiled from two curated Agent Skills, copied verbatim here:

| Path | What it is |
|---|---|
| `13f-analyzer/SKILL.md` | Usage of the analysis scripts: one-fund summary, two-quarter change, top holders of a CUSIP. |
| `13f-analyzer/scripts/one_fund_analysis.py` | Summary (holdings, AUM, stock holdings, stock AUM) and top-10 buys/sells between quarters. |
| `13f-analyzer/scripts/holding_analysis.py` | Top-k accession numbers holding a CUSIP by summed VALUE. |
| `fuzzy-name-search/SKILL.md` | Usage and sample output of the search scripts. |
| `fuzzy-name-search/scripts/search_fund.py` | Fuzzy (rapidfuzz WRatio) filer-name search on COVERPAGE; exact search by accession number. |
| `fuzzy-name-search/scripts/search_stock_cusip.py` | Fuzzy issuer-name search to CUSIP on INFOTABLE. |

Target task: `instruction.md` style questions (fund AUM, number of stocks, top increased
positions between Q2 and Q3 2025 by dollar value, top-3 managers holding Palantir) against the
SEC Form 13F data sets unpacked to `/root/2025-q2` and `/root/2025-q3`, answers written to
`/root/answers.json`. Container: Ubuntu 24.04, python3 3.12, pandas 2.3.3, rapidfuzz 3.14.3.

## Intent

One procedure covering the whole workflow both source skills describe: search names to
accession numbers / CUSIPs, analyze the selected filings, and answer. It is parameterized by
quarter folders and search terms, so a different instance (other funds, stocks, quarters, or
data) runs unchanged; nothing about the expected answers is hardcoded.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `search` | execution | Fuzzy matching, per-filing aggregates and the suggestion rules are deterministic code (`scripts/search.py`). |
| `select-entities` | client_task | Deciding which filer the task means ("founded by Jim Simons", "Warren Buffett's") is judgment over an open answer space (accession numbers, CUSIPs), so it cannot be a fixed-label decision. The script pre-ranks and flags `ambiguous` so the judgment is narrow. |
| `analyze` | execution | AUM, counts, per-CUSIP deltas and holder rankings are arithmetic (`scripts/analyze.py`). |
| `compose-answers` | client_task | Mapping free-text questions to the task's answer keys and types needs reading the task statement; the template carries the question→field mapping. |
| `write-answers` | execution | Writing JSON and checking types is mechanical (`scripts/write_answers.py`). |
| `answer-check` | decision (noul) | Whether the written object matches the task schema is a yes/no judgment with a written-down boundary; threshold 0.2 because a wrong-format file fails the whole task. |
| `route-answers` | router | `true` → end, `false` → repair. |
| `repair-answers` | client_task | Rewriting the file against the schema needs generation. |

Scripts: one shared loader (`f13common.py`) plus one script per execution step. INFOTABLE.tsv
(~340 MB, ~3.3M rows) is streamed in 400k-row chunks with only the needed columns
(peak ~0.9 GB RSS, ~6–9 s per step on the real files).

## Deliberate changes from the source scripts (bugs found against the real files)

1. **Case-sensitive fuzzy match** (`search_fund.py`, `process.extract` without a processor):
   "renaissance technologies" ranked "Headlands Technologies LLC" first and never found
   "RENAISSANCE TECHNOLOGIES LLC". Fixed with `processor=utils.default_process`.
2. **`ISAMENDMENT == "N"` filter** (`search_fund.py`): most original filings leave
   ISAMENDMENT blank (5k of 10k cover pages per quarter, including Renaissance), so the source
   silently skipped them. Now only `Y` marks an amendment.
3. **Missing commas in `title_class_of_stocks`** (both analyzer and stock search): Python
   concatenated 16 entries into one string, so only 9 classes matched. Fixed list kept in
   `f13common.py` for an informational count only. Even fixed, TITLEOFCLASS is free text and
   misses stocks ("shs", "ord", "com ser c"); for Berkshire it changes the top-5 increases
   (Alphabet class C, a new position, is "cap stk cl c"). Stock basis is now share positions:
   `SSHPRNAMTTYPE == SH` and empty `PUTCALL`, counted as distinct CUSIPs.
4. **`holding_analysis.py` read `/root/INFOTABLE.tsv`** (no quarter folder) and ignored
   `--quarter`. Now reads the selected quarter.
5. **Top holders double counting**: managers can file an original plus a "NEW HOLDINGS"
   amendment that repeats the whole table (JPMorgan in Q3). Ranking now keeps each manager's
   largest filing, limited to the quarter's main report period and non-NOTICE filings, and
   reports names (the task asks for manager names, the source printed accession numbers).
6. **Stock search** used `2025-q2` hardcoded and the first-seen name per CUSIP; a filer's
   typo (a "PALANTIR" label on P&G's CUSIP) or a one-letter issuer name could outrank the
   real CUSIP. Now searches the current quarter and ranks CUSIPs by how many filings name them
   with a close match (`matching_filings`, `matched_share`).
7. **pct change with zero baseline** was divided by 1 (yielding the dollar amount as a
   "percent"); now `null` with `status: new`.
8. **Exit on no stock rows** (`one_fund_analysis.py` `exit(1)`): replaced by a `warning` in
   the summary so a NOTICE pick is visible to the agent instead of aborting the run.
9. **Fund pick**: the source left "best match" to the reader; Berkshire's insurance
   affiliates tie with the parent at the same score but file 13F NOTICEs. The script prefers
   names within 2 points of the top score that filed holdings for the main period, then the
   largest; `select-entities` confirms.

## Completeness check (source item → where it lives)

| Source item | Location in the skill |
|---|---|
| 13f-analyzer: one-fund summary (total holdings, AUM, stock holdings, stock AUM) | `analyze` → `fund_summaries` (`total_holdings`, `aum`, `stock_holdings`, `stock_value`); mapping in `assets/compose_answers.md` |
| 13f-analyzer: change between quarters, newly purchased / sold ranked by notional value, pct change | `analyze` → `holding_changes.top_increases/top_decreases` (≥10 rows, `pct_change`, `status`, `n_new_positions`, `n_exited_positions`) |
| 13f-analyzer: group by CUSIP, first name, summed VALUE; outer merge, fill 0 | `analyze.py` `by_cusip` / `compare` |
| 13f-analyzer: top-k funds holding a CUSIP by value | `analyze` → `top_holders.ranking` (and `ranking_incl_options`) |
| `--quarter`, `--accession_number`, `--baseline_*`, `--topk` arguments | start inputs `quarter`, `baseline_quarter`, `topk`; accessions via `selection` |
| `data_root = "/root"` | start input `data_root`; nested-folder fallback in `f13common.quarter_dir` |
| title_class_of_stocks list | `f13common.TITLE_CLASS_OF_STOCKS` (fixed), `title_list_*` fields; anti-pattern entry |
| fuzzy-name-search: fuzzy fund search with WRatio, `--keywords`, `--quarter`, `--topk` | `search` (`fund_queries`, per quarter, `topk`) |
| fuzzy-name-search: printed fields (accession, period, name, street, city, state, 13F file number) | candidate `filings[].accession_number/period`, `name`, `location`, `form13f_file_number` |
| fuzzy-name-search: exact search by accession number | `search`: an accession-number query is an exact lookup; `analyze` fails clearly on an unknown accession |
| fuzzy-name-search: non-amendment preference | suggestion rule + `select-entities` template (fixed per change 2) |
| fuzzy-name-search: stock CUSIP search by name, lowercase, dedupe by CUSIP | `search` → `stock_candidates` (change 6) |
| "you don't have to provide the accurate name" (Levenshtein-based fuzzy search) | description, `fund_queries`/`stock_queries` descriptions |
| Accession numbers change each reporting season (instruction) | `select-entities` template, anti-patterns |

## Deliberate drops

- **CLI invocation examples** (`python3 scripts/... --keywords ...`) and the printed
  text-report formats: replaced by the step stdin/stdout JSON contract; same information is in
  the structured outputs.
- **Sample Bridgewater / Palantir output blocks** in fuzzy-name-search/SKILL.md: illustrative
  only; the functional test reproduced them (Bridgewater Associates 0001172661-25-003151,
  Palantir 69608A108).
- **Docstring text in the source scripts** (mentions `coverpage`/`limit` args that do not
  exist): stale, no behavior.
- **Hardcoded `2025-q2` stock search universe**: replaced by the current quarter (change 6).
