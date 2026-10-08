Answer the request from the computed results.

Request:
{question}

Analysis plan:
{analysis_plan}

Results (VALUE fields are US dollars):
{results}

Rules:
- Answer every question asked, with numbers taken from the results, not estimated. Keep full
  precision unless the user asks for rounding; state units (dollars) and the quarter.
- "Number of holdings" = `total_holdings`; "AUM" = `total_aum`; "number of stock holdings" /
  "stock AUM" = `stock_holdings` / `stock_aum` (the plan's `stock_list_mode`; default `as_shipped`
  is the source skill's definition: common/class A shares, excluding ADRs, class B, ordinary shares).
  Give that figure as the answer; when `stock_holdings_intended` differs, add one line noting the
  broader count that also includes ADRs, class B, and ordinary shares.
- Buys/sells are ranked by change in market value (`abs_change`); name each with CUSIP. For new
  positions say "new position" rather than quoting `pct_change`. Mention `share_change` when price
  moves could explain a value change.
- Top holders: list manager name, accession number, and holding value in rank order; flag
  `off_period_or_amendment` holders and large `option_value_included` (holding_value includes option
  rows, as in the source; the search step's `total_value_excl_options` does not).
- If any `errors` appear, say what could not be computed and why.
- If the request specifies an output file or format (e.g. a JSON file with given keys), write it
  exactly in that format and path, with values as plain numbers/strings, and also summarize it.

Produce `answer` (string): the final answer text. `results` is already in the state; you need not resend it.
