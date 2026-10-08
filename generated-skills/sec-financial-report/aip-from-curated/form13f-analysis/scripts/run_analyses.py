"""AIP step: run the planned 13F analyses on the resolved accession numbers and CUSIPs.

stdin:  {"currentState": {"analysis_plan": {"fund_summaries": [{"accession_number", "quarter"}],
                                            "comparisons": [{"accession_number", "quarter",
                                                             "baseline_accession_number", "baseline_quarter"}],
                                            "top_holders": [{"cusip", "quarter", "topk"?}],
                                            "stock_list_mode"?: "as_shipped" | "intended"},
                          "data_root"?: "/root"},
         "assets": {"stock_title_classes": "<json>"}, "expects": [...]}
stdout: {"results": {"fund_summaries": [...], "comparisons": [...], "top_holders": [...], "errors": [...]}}
"""
import json
import sys

import f13lib


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    raw = (payload.get("assets") or {}).get("stock_title_classes")
    classes = f13lib.load_title_classes(raw)
    plan = state.get("analysis_plan") or {}
    mode = plan.get("stock_list_mode") or "as_shipped"
    if mode not in classes:
        mode = "as_shipped"
    root = state.get("data_root") or f13lib.DEFAULT_DATA_ROOT
    res = {"stock_list_mode": mode, "value_units": "US dollars (VALUE rounded to the nearest dollar)",
           "fund_summaries": [], "comparisons": [], "top_holders": [], "errors": []}
    filings = {}
    for item in plan.get("fund_summaries") or []:
        try:
            res["fund_summaries"].append(f13lib.fund_summary(item["accession_number"], item["quarter"],
                                                             classes, mode, root))
        except (f13lib.F13Error, KeyError) as e:
            res["errors"].append({"analysis": "fund_summary", "item": item, "error": str(e)})
    for item in plan.get("comparisons") or []:
        try:
            res["comparisons"].append(f13lib.compare(item["accession_number"], item["quarter"],
                                                     item["baseline_accession_number"], item["baseline_quarter"],
                                                     classes, mode, int(item.get("topn") or 10), root))
        except (f13lib.F13Error, KeyError) as e:
            res["errors"].append({"analysis": "comparison", "item": item, "error": str(e)})
    for item in plan.get("top_holders") or []:
        try:
            q = item["quarter"]
            if q not in filings:
                filings[q] = f13lib.filings_table(root, q)
            res["top_holders"].append(f13lib.top_holders(item["cusip"], q, int(item.get("topk") or 10),
                                                         root, filings[q]))
        except (f13lib.F13Error, KeyError) as e:
            res["errors"].append({"analysis": "top_holders", "item": item, "error": str(e)})
    print(json.dumps({"results": res}, default=str))


if __name__ == "__main__":
    main()
