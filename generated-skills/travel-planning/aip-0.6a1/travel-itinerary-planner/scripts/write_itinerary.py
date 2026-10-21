"""Execution step: final gate. Re-check the itinerary against the database, then write it.

Serves two steps: `write-itinerary` (state holds `plan`, prints `write_report`) and
`write-repaired` (state holds `repaired_plan`, prints `repaired_write_report`).

stdin:  {"state": {"plan" | "repaired_plan": {...}, "candidates": {...}, "data_dir": "...",
                   "output_path": "..."}, ...}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import plan_check
import travel_db as db

KEYS = ["day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"]


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("state", payload)
    repaired = "repaired_plan" in state
    itin = state["repaired_plan"] if repaired else state["plan"]
    if isinstance(itin, str):
        itin = json.loads(itin)
    r = state["candidates"]["request"]
    data_dir = state.get("data_dir") or db.DEFAULT_DATA_DIR

    # Emit exactly the documented shape: ordered day keys, string fields, int day.
    clean = {"plan": [], "tool_called": list(dict.fromkeys(itin.get("tool_called") or []))}
    for i, d in enumerate(itin.get("plan") or [], start=1):
        row = {k: d.get(k, "-") for k in KEYS}
        row["day"] = int(row["day"]) if str(row["day"]).isdigit() else i
        for k in KEYS[1:]:
            row[k] = "-" if row[k] in (None, "") else str(row[k])
        clean["plan"].append(row)

    chk = plan_check.check(clean, r, data_dir)
    if not clean["plan"]:
        print("refusing to write an empty plan", file=sys.stderr)
        sys.exit(1)
    out = Path(state["output_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = {"path": str(out), "days": len(clean["plan"]), "violations": chk["violations"],
              "cost": chk["cost"], "route": chk["route"], "cuisines_covered": chk["cuisines_covered"]}
    json.dump({("repaired_write_report" if repaired else "write_report"): report}, sys.stdout, default=str)


if __name__ == "__main__":
    main()
