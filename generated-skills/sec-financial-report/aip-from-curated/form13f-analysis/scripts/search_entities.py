"""AIP step: fuzzy-search the funds and stocks named in the request.

stdin:  {"currentState": {"fund_queries": [{"keywords", "quarter"}], "stock_queries": [{"keywords", "quarter"?}],
                          "data_root"?: "/root", "topk"?: 10}, "assets": {...}, "expects": [...]}
stdout: {"fund_candidates": [...], "stock_candidates": [...], "search_errors": [...]}
"""
import json
import sys

import f13lib


def main():
    state = json.load(sys.stdin).get("currentState", {})
    root = state.get("data_root") or f13lib.DEFAULT_DATA_ROOT
    topk = int(state.get("topk") or 5)
    errors, funds, stocks = [], [], []
    filings, universes = {}, {}
    for q in state.get("fund_queries") or []:
        quarter = q.get("quarter") or "2025-q2"
        try:
            if quarter not in filings:
                filings[quarter] = f13lib.filings_table(root, quarter)
            funds.append(f13lib.search_fund(q.get("keywords", ""), quarter, topk, root, filings[quarter]))
        except f13lib.F13Error as e:
            errors.append({"query": q, "error": str(e)})
    for q in state.get("stock_queries") or []:
        quarter = q.get("quarter") or "2025-q2"
        try:
            if quarter not in universes:
                universes[quarter] = f13lib.stock_universe(root, quarter)
            stocks.append(f13lib.search_stock(q.get("keywords", ""), quarter, topk, root, universes[quarter]))
        except f13lib.F13Error as e:
            errors.append({"query": q, "error": str(e)})
    print(json.dumps({"fund_candidates": funds, "stock_candidates": stocks, "search_errors": errors}, default=str))


if __name__ == "__main__":
    main()
