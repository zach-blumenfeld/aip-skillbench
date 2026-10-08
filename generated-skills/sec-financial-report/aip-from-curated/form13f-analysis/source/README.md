# form13f-analysis — source and compilation notes

## Provenance

Compiled from two curated Agent Skills, copied verbatim into this folder:

- `13f-analyzer/` — `SKILL.md`, `scripts/one_fund_analysis.py` (one-quarter summary and
  quarter-over-quarter buy/sell ranking for one fund), `scripts/holding_analysis.py` (top-k funds
  holding a CUSIP).
- `fuzzy-name-search/` — `SKILL.md`, `scripts/search_fund.py` (fuzzy fund-name search or exact
  accession-number lookup in COVERPAGE), `scripts/search_stock_cusip.py` (fuzzy issuer-name → CUSIP).

Environment facts were taken from the task's `Dockerfile` (Ubuntu 24.04, python3, pandas 2.3.3,
rapidfuzz 3.14.3; `13f-2025-q2.zip` unzipped and moved to `/root/2025-q2`, `13f-2025-q3.zip`
unzipped to `/root/2025-q3`) and from the real SEC data sets themselves (`FORM13F_readme.htm`,
`FORM13F_metadata.json`, and profiling of COVERPAGE / INFOTABLE).

The two skills describe one workflow: resolve names → accession numbers / CUSIPs, then analyze.
They are compiled into one graph:

```
plan-request (client_task) → search-entities (execution) → resolve-entities (client_task)
  → run-analyses (execution) → write-answer (client_task) → end
```

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| plan-request | client_task | Turning a free-form question into a list of name queries per quarter is open-ended extraction; there is no fixed answer space. |
| search-entities | execution | Fuzzy matching (rapidfuzz WRatio), filing lookup, and per-CUSIP aggregation are deterministic code; source scripts were already code. |
| resolve-entities | client_task | Choosing which of N candidate managers / CUSIPs the user means is a selection over an input-dependent candidate list (not a fixed label set), so a `decision` step cannot express it. The script supplies a deterministic default (`suggested_accession_number`, tie ordering) so the judgment is narrow. |
| run-analyses | execution | All metrics are numeric aggregations defined by the source scripts. |
| write-answer | client_task | Prose / user-specified output format generation. |

No `decision` or `router` step: every request runs the same pipeline, and the analyses to run are
lists inside `analysis_plan` (empty lists skip an analysis), so there is no branch to take.

Scripts: `scripts/f13lib.py` holds all loaders and analyses (also a CLI mirroring the four source
commands, for ad-hoc re-searching); `scripts/search_entities.py` and `scripts/run_analyses.py` are
the thin AIP step wrappers. `assets/stock_title_classes.json` holds the stock TITLEOFCLASS list.

## Behavior preserved exactly (verified on the real 2025-q2 / 2025-q3 data)

- Fund summary: holdings = INFOTABLE row count; AUM = sum of VALUE over all rows; stock holdings /
  stock AUM = rows whose lowercased TITLEOFCLASS is in the stock list; error if no stock rows.
- Comparison: per-CUSIP sum of stock VALUE, outer join, missing → 0, `ABS_CHANGE = VALUE − VALUE_base`,
  `PCT_CHANGE = ABS_CHANGE / VALUE_base.replace(0, 1)`, top 10 buys (largest positive) and top 10
  sells (most negative). Renaissance Technologies Q2→Q3 output is identical to the source script.
- Top holders: sum VALUE over all rows of the CUSIP per accession number, descending, top-k
  (Palantir 69608A108 Q3 ranking identical to the source script with its path fixed).
- Fund search: rapidfuzz `process.extract(..., scorer=fuzz.WRatio, limit=topk)` over unique
  FILINGMANAGER_NAME; exact lookup by accession number. Stock search: WRatio on lowercased issuer
  names, CUSIP uppercased, default quarter 2025-q2.
- Stock list: the source list is missing commas after `"com shs"`, so Python concatenates the next
  17 entries into one string that never matches. The effective list is kept as `as_shipped`
  (default, reproduces the source numbers); the list as written is kept as `intended` and both
  figures are reported (`stock_holdings_as_shipped` / `stock_holdings_intended`).

## Deliberate fixes (source behavior that was wrong for this data)

- `holding_analysis.py` read `/root/INFOTABLE.tsv`, which does not exist; it now reads
  `/root/<quarter>/INFOTABLE.tsv`.
- `search_fund.py` kept only `ISAMENDMENT == "N"`; ~half of filings have it blank (e.g. Renaissance
  Technologies 2025-q3), so those funds were silently unfindable. Blank is now treated as original.
- Fund search is case-insensitive (`utils.default_process`); the source was case-sensitive.
- Fund matches list every filing of the manager (notice, amendment, late older-period filings) and
  suggest the original holdings report for the folder's main period; equal scores are ordered
  holdings filers first, larger first (source: first non-amendment row in rapidfuzz order).
- `search_stock_cusip.py` hardcoded 2025-q2 and returned duplicate (name, CUSIP) rows; it now takes a
  quarter, returns one row per CUSIP with filer-row count and total value, and breaks ties by value
  so the real common stock comes first. It no longer filters by the (broken) stock list, so ADR-only
  issuers are findable.
- CUSIPs are uppercased before matching/grouping (≈7.6k INFOTABLE rows use lowercase).
- INFOTABLE is read in chunks with `usecols` (≈340 MB per quarter) to bound memory.
- Extra context added to outputs: shares and share change, new/exited flags, option value included,
  manager names and filing flags for top holders, both stock-list figures.

## Completeness check (source line → pack location)

| Source content | Where in the pack |
|---|---|
| 13f-analyzer description (holdings, AUM, change between quarters) | frontmatter description, `purpose`, trigger_when |
| one-quarter summary command + printed stats | `run-analyses` → `f13lib.fund_summary`; CLI `fund-summary` |
| two-quarter comparison command, baseline semantics, top buys/sells | `resolve_entities.md` (comparisons), `f13lib.compare`, CLI `compare` |
| top-k holders command | `resolve_entities.md` (top_holders), `f13lib.top_holders`, CLI `top-holders` |
| fuzzy fund search by keywords, topk 10, example output fields | `search-entities`, `f13lib.search_fund` (all cover fields kept), CLI |
| exact search by accession number | `f13lib.search_fund` accession branch; `plan_request.md` (accession as keywords) |
| fuzzy stock search → CUSIP, palantir example | `f13lib.search_stock`; data guide gotcha (Palantir → 69608A108) |
| "names need not be exact; Levenshtein-based fuzzy search" | `purpose`, trigger_when, search step |
| title_class_of_stocks list | `assets/stock_title_classes.json` (`as_shipped` + `intended`) |
| data_root `/root`, quarter folders | f13lib `DEFAULT_DATA_ROOT`, data guide layout, `plan_request.md` |
| ERROR on no stock rows | `F13Error` → `results.errors`, `write_answer.md` error rule |
| "No fund found with ACCESSION_NUMBER" | `search_fund` note |

## Deliberate-drop log

- Exact console print formats (`** Rank 1 (score = …) **`, `[1] CUSIP: …`): replaced by JSON
  fields carrying the same values; the step contract requires JSON stdout.
- Duplicate stock search results (the source example shows Palantir twice): an artifact of not
  deduplicating names; dropped by design.
- `exit(1)` on missing stock rows: replaced by a per-item error record so other analyses still run.
- Docstring text in the source scripts that mislabels functions ("Fuzzy search fund information"
  on the stock search, `limit` args that do not exist): inaccurate, not actionable.
