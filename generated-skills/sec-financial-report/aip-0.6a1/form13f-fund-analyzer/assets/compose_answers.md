Task statement (it defines the answer keys and the type of each value):
{task_statement}

Entity choices: {selection_notes}
Fund summaries: {fund_summaries}
Holding changes: {holding_changes}
Top holders: {top_holders}

Fill every key of the task's answer schema from these results, nothing invented:
- AUM / total portfolio value: fund_summaries aum (sum of VALUE over every row of the
  filing, whole US dollars, equals summarypage_value_total). Write a plain JSON number,
  no scaling to thousands or millions, no currency text.
- Number of stocks / holdings held: fund_summaries stock_holdings (distinct CUSIPs among
  share positions, no options). It equals total_holdings when each CUSIP is reported
  once; when they differ, total_holdings counts rows (one security split across
  sub-managers) and is not the number of stocks. title_list_stock_rows is the source
  skill's TITLEOFCLASS heuristic and undercounts; do not report it.
- Stocks with increased investment / top buys from baseline to current quarter:
  holding_changes top_increases in order, as CUSIPs unless the task asks for names;
  ranked by abs_change (dollar value change), take exactly as many as asked.
- Largest holders / top fund managers of a stock: top_holders ranking (share positions)
  in order, manager_name exactly as filed; take exactly as many as asked. Use
  ranking_incl_options only if the task counts options exposure.
Read references/form13f-data.md when a question asks for a figure not listed here or a
result looks inconsistent (e.g. a zero AUM, a NOTICE filing, a value off by 1000x).
