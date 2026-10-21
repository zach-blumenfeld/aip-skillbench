"""Write the furthest in-plate earthquake to the answer JSON file.

stdin:  {"state": {"furthest": {...}, "output_path": "..."}}
stdout: {"answer_path": "...", "answer": {...}}
"""
import json
import os
import sys

FIELDS = ["id", "place", "time", "magnitude", "latitude", "longitude", "distance_km"]


def main():
    state = json.load(sys.stdin)["state"]
    furthest = state["furthest"]
    missing = [k for k in FIELDS if k not in furthest]
    if missing:
        print(f"furthest record lacks fields: {missing}", file=sys.stderr)
        sys.exit(1)
    answer = {k: furthest[k] for k in FIELDS}
    path = os.path.abspath(state["output_path"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(answer, fh, indent=2, ensure_ascii=False)
    print(json.dumps({"answer_path": path, "answer": answer}))


if __name__ == "__main__":
    main()
