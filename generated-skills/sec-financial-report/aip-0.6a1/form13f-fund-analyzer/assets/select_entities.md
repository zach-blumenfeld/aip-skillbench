Task statement:
{task_statement}

Current quarter: {quarter}. Baseline quarter (empty = none): {baseline_quarter}.

Fund search results per query and quarter:
{fund_candidates}

Stock search results per query:
{stock_candidates}

Choose the filing and security the task actually means.
Funds:
- Pick the filer the task describes, using its hints (founder, famous owner). The famous
  parent files the holdings report; affiliates with near-identical names usually file a
  13F NOTICE with no holdings (e.g. "Berkshire Hathaway Inc" vs "Berkshire Hathaway Life
  Insurance Co of Nebraska"; "RENAISSANCE TECHNOLOGIES LLC" vs "RenaissanceRe" or
  "Renaissance Investment Holdings"). Unrelated names that merely share a word are wrong.
  location and form13f_file_number tell same-named filers apart (Bridgewater Associates is
  in Westport, CT). A query that is an accession number was looked up exactly.
- Pick one accession per quarter: the original (is_amendment false) 13F HOLDINGS or
  COMBINATION REPORT for the quarter's main period with n_holdings above zero. A fund
  files a new accession number every quarter, so pick it separately for each quarter.
  Take a RESTATEMENT amendment instead only if the task asks for restated figures.
- When "ambiguous" is true, or the suggested name does not fit the task's description,
  choose from the candidates yourself; never pick a filing with zero holdings.
Stocks:
- Pick the CUSIP most filings use for the company's common shares: the highest
  matching_filings with matched_share near 1. CUSIPs that end in 9xx with few filings are
  option listings; a CUSIP with tiny matched_share is a filer's typo for another company.
- If the company has several share classes (e.g. Alphabet class A and C) and the task
  names none, pick the class with the most matching filings and say so.
Use each fund query string and each stock query string as its label.
