# SEC Form 13F data sets — field guide

Load this when a result looks wrong, a fund or stock does not resolve, or the request
needs a column the scripts do not report.

## Layout in the task container

- `/root/2025-q2/` — SEC "01JUN2025-31AUG2025_form13f" data set: filings made 1 Jun–31 Aug 2025,
  almost all for report period `30-JUN-2025` (Q2 2025).
- `/root/2025-q3/` — filings for report period `30-SEP-2025` (Q3 2025).
- Each folder: `COVERPAGE.tsv`, `INFOTABLE.tsv`, `SUMMARYPAGE.tsv`, `SUBMISSION.tsv`, `SIGNATURE.tsv`,
  `OTHERMANAGER.tsv`, `OTHERMANAGER2.tsv`, `FORM13F_metadata.json`, `FORM13F_readme.htm`.
  Tab-separated, one header row. INFOTABLE is ~340 MB / ~3.3M rows; read it with `usecols` or in chunks.
- The quarter folder is the "quarter" argument everywhere (`2025-q2`, `2025-q3`). A fund gets a
  **different accession number in each quarter**; never reuse a Q2 accession number on Q3 data.

## Key columns

| Table | Column | Meaning |
|---|---|---|
| all | `ACCESSION_NUMBER` | One EDGAR submission (one filing), format `0001172661-25-003151`. Join key. |
| COVERPAGE | `FILINGMANAGER_NAME` | Fund / manager name searched by the fuzzy fund search. |
| COVERPAGE | `REPORTCALENDARORQUARTER` | Period the filing reports (e.g. `30-SEP-2025`). Late filings for older periods appear in every folder. |
| COVERPAGE | `ISAMENDMENT` | `Y`, `N`, **or blank** (blank ≈ half of rows, means original filing). |
| COVERPAGE | `AMENDMENTTYPE` | `RESTATEMENT` (replaces the whole table) or `NEW HOLDINGS` (adds rows). |
| COVERPAGE | `REPORTTYPE` | `13F HOLDINGS REPORT`, `13F COMBINATION REPORT` (both have holdings), `13F NOTICE` (no holdings; holdings are reported by another manager). |
| SUMMARYPAGE | `TABLEENTRYTOTAL`, `TABLEVALUETOTAL` | Filer-reported row count and total value; cross-check for the computed totals. |
| SUBMISSION | `SUBMISSIONTYPE`, `FILING_DATE`, `CIK` | `13F-HR`, `13F-NT`, `13F-HR/A`, `13F-NT/A`. |
| INFOTABLE | `NAMEOFISSUER`, `TITLEOFCLASS`, `CUSIP` | Security. CUSIP is 9 chars; some filers write it lowercase. |
| INFOTABLE | `VALUE` | Market value **in US dollars** (rounded to the dollar since 3 Jan 2023; older data was thousands). |
| INFOTABLE | `SSHPRNAMT`, `SSHPRNAMTTYPE` | Share count (`SH`) or principal amount (`PRN`). |
| INFOTABLE | `PUTCALL` | `Put` / `Call` for option rows, blank otherwise. Option rows carry the underlying's CUSIP. |

## Metric definitions used by this skill (from the source 13f-analyzer scripts)

- **Total number of holdings** = count of INFOTABLE rows for the accession number (not distinct CUSIPs;
  a filer may split one security over several rows by discretion/manager).
- **AUM** = sum of `VALUE` over all those rows (includes options, bonds, ETFs).
- **Stock holdings / stock AUM** = rows whose lowercased `TITLEOFCLASS` is in
  `assets/stock_title_classes.json`. Default list `as_shipped` = what the source scripts actually
  evaluate (`com`, `common stock`, `cl a`, `com new`, `class a`, `stock`, `common`, `com cl a`,
  `com shs`); `intended` adds ADRs, `cl b`, `ord shs`, `equity`, `cmn`, etc. Both are reported.
- **Buys / sells between quarters** = per-CUSIP change in summed stock `VALUE`
  (current − baseline), ranked by absolute dollar change; positions absent in one quarter count as 0.
  This is a change in **market value**, so price moves count; `share_change` is reported alongside.
  `pct_change` divides by the baseline value with 0 replaced by 1 (source behavior), so for new
  positions it is meaningless — say "new position" instead.
- **Top holders of a stock** = per accession number, sum of `VALUE` over every row with that CUSIP
  (option rows included, as in the source); `option_value_included` shows how much is options.

## Gotchas

- The source fund search kept only `ISAMENDMENT == "N"` rows, silently dropping funds whose flag is
  blank (e.g. RENAISSANCE TECHNOLOGIES LLC in 2025-q3). The pack treats blank as "original".
- Fuzzy matching is case-insensitive here (the source fund search was case-sensitive). Similar names
  tie (e.g. "bridgewater" → Bridgewater Associates, LP and Bridgewater Advisors Inc. both 81.8):
  pick by the user's wording, location, and size (`holdings_value`), not by rank alone. The pack
  orders equal scores with holdings-report filers first, then by size (the source kept rapidfuzz order).
- A manager can have several filings in one folder: notice + holdings report, an original plus an
  amendment, or late filings for older periods. Use the original holdings report for the folder's
  main period (`suggested_accession_number`); use a `RESTATEMENT` amendment only if asked.
- Stock search over names returns option and odd CUSIPs with the same name; the real common stock
  is the match with by far the most `infotable_rows` / `total_value_excl_options` (Palantir → `69608A108`).
- Companies with several share classes have several CUSIPs (Alphabet class A vs class C) — confirm
  which one the request means or report each.
- Top-holders ranking is per filing: affiliated entities (e.g. several BlackRock or Vanguard filers)
  appear separately, and an `off_period_or_amendment` holder is a late or amended filing.
