"""Write the final period to the requested output file at 5 decimal places."""

from __future__ import annotations

import json
import os
import sys


def main() -> None:
    payload = json.loads(sys.stdin.read())
    state = payload["currentState"]
    period = float(state["period"])
    output_path = state["output_path"]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as fh:
        fh.write(f"{period:.5f}\n")

    print(json.dumps({
        "period": round(period, 5),
        "output_path": output_path,
        "written": True,
    }))


if __name__ == "__main__":
    main()
