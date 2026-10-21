# SEC Form 13F data sets — what the columns mean and how questions map to them

## Layout

One folder per quarterly data set (e.g. `/root/2025-q2`, `/root/2025-q3`), tab-separated files:

| File | Key columns | Notes |
|---|---|---|
| `COVERPAGE.tsv` | ACCESSION_NUMBER, REPORTCALENDARORQUARTER, ISAMENDMENT, AMENDMENTTYPE, FILINGMANAGER_NAME, REPORTTYPE, FORM13FFILENUMBER | One row per filing. |
| `INFOTABLE.tsv` | ACCESSION_NUMBER, NAMEOFISSUER, TITLEOFCLASS, CUSIP, VALUE, SSHPRNAMT, SSHPRNAMTTYPE, PUTCALL, INVESTMENTDISCRETION, OTHERMANAGER | One row per holding line; ~3M rows, ~340 MB. |
| `SUMMARYPAGE.tsv` | ACCESSION_NUMBER, TABLEENTRYTOTAL, TABLEVALUETOTAL | Filer-reported row count and value total; cross-check. |
| `SUBMISSION.tsv` | ACCESSION_NUMBER, FILING_DATE, SUBMISSIONTYPE (13F-HR, 13F-HR/A, 13F-NT), CIK, PERIODOFREPORT | Filing date when two filings compete. |
| `OTHERMANAGER*.tsv`, `SIGNATURE.tsv` | | Not needed for these questions. |

A data set is named by its filing window, not its report period: the "2025-q3" folder holds
filings made in that window, mostly for period 30-SEP-2025, plus late filings and amendments
for older periods. The scripts take the most common REPORTCALENDARORQUARTER as the quarter's
main period and ignore other periods when ranking holders.

## Semantics

- **Accession number** identifies one filing. A manager gets a new one every quarter.
- **REPORTTYPE**: `13F HOLDINGS REPORT` (all holdings), `13F COMBINATION REPORT` (some holdings,
  rest reported by another manager), `13F NOTICE` (no holdings; another manager reports them —
  typical for subsidiaries such as Berkshire's insurance companies).
- **ISAMENDMENT**: `Y` = amendment; blank or `N` = original. AMENDMENTTYPE `RESTATEMENT`
  replaces the original; `NEW HOLDINGS` adds rows, though some filers resubmit the full table.
- **VALUE**: market value in whole US dollars (since 2023; earlier data sets used thousands).
  Sum over a filing equals SUMMARYPAGE TABLEVALUETOTAL.
- **SSHPRNAMTTYPE**: `SH` shares or `PRN` principal amount (bonds/convertibles).
- **PUTCALL**: `Put`/`Call` for option rows; VALUE there is the underlying's value, not money
  invested. Blank for share positions.
- **TITLEOFCLASS**: free text ("COM", "CL A", "SHS", "ORD", "CAP STK CL C", "Stock"...). Not a
  reliable stock filter.
- **CUSIP**: 9 characters; the same company has different CUSIPs per share class (Alphabet A
  02079K107 vs C 02079K305 in these files). Option-series CUSIPs (e.g. ending 9xx) appear rarely.
- A filer may report one CUSIP on several rows (per sub-manager or discretion type); group by
  CUSIP before counting stocks or comparing quarters.

## Question → field (from `analyze` output)

| Question | Field | Definition |
|---|---|---|
| AUM / portfolio value of fund X | `fund_summaries[X][quarter].aum` | Sum of VALUE over every row of the selected filing. |
| How many stocks / holdings fund X holds | `fund_summaries[X][quarter].stock_holdings` | Distinct CUSIPs among share positions (SH, no PUTCALL). `total_holdings` = raw rows; `distinct_cusips` = all distinct CUSIPs incl. options/bonds. |
| Stock-only value | `stock_value` | VALUE summed over share positions. |
| Top N stocks with increased investment (by $) | `holding_changes[X].top_increases[:N].cusip` | Per CUSIP: current VALUE − baseline VALUE over share positions, positive only, descending. `status` new/held. |
| Top N sold / decreased | `holding_changes[X].top_decreases[:N]` | Most negative abs_change first; `exited` = fully sold. |
| Newly bought / exited count | `n_new_positions`, `n_exited_positions` | |
| Percent change | `pct_change` | abs_change / baseline value; null for new positions. |
| Top N managers holding stock S | `top_holders[S].ranking[:N].manager_name` | Per filing VALUE of share positions in that CUSIP for the main period, non-NOTICE; each manager's largest filing; descending. `ranking_incl_options` adds option rows. |

Shares (`shares`, `shares_base`) tell a real purchase from a price move: a value increase with
flat shares is appreciation. "Increased investment ranked by dollar value increase" means
abs_change of VALUE unless the task says shares.

## Source-skill conventions kept for reference

The source 13f-analyzer reported "Number of stock holdings" using a TITLEOFCLASS list; its
missing commas made it match only nine classes. `title_list_stock_rows` and
`title_list_top_increases` reproduce that heuristic (commas fixed) for comparison only.
