Read the request and list every fund and stock it names, so the search step can resolve them.

Request:
{question}

Produce these keys for the next step:

- `fund_queries` (list of objects): one object per fund per quarter you will need, each with
  `keywords` (the fund/manager name as the user wrote it, or an accession number if given) and
  `quarter` (data-folder name: `2025-q2` for the quarter ending 30-JUN-2025, `2025-q3` for 30-SEP-2025).
  A quarter-over-quarter comparison needs the fund searched in BOTH quarters — each quarter
  has its own accession number. Empty list if no fund is named.
- `stock_queries` (list of objects): one object per stock, with `keywords` (company name, or a
  9-character CUSIP if given) and `quarter` (the quarter whose holders are asked about; default `2025-q2`).
  Empty list if no stock is named.
- `data_root` (string, optional): parent folder of the quarter folders (`<data_root>/2025-q2/COVERPAGE.tsv`).
  Omit it when the data is in `/root` (the task container). Include it whenever the request or
  environment puts the 13F files elsewhere; later steps read it from the state.

Map "Q2 2025", "June 2025", "second quarter" → `2025-q2`; "Q3 2025", "September 2025", "latest
quarter" → `2025-q3`. Copy names the way the user wrote them; do not guess legal names.
