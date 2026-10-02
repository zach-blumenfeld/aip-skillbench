#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    answer = str(state["answer"]).strip()
    answer_path = Path(state["answer_path"])

    if not NUMBER_RE.match(answer):
        raise ValueError(
            f"answer must match ^-?\\d+(\\.\\d+)?$ (integer or decimal only). Got: {answer!r}"
        )

    answer_path.parent.mkdir(parents=True, exist_ok=True)
    answer_path.write_text(answer + "\n", encoding="utf-8")

    json.dump({"answer_written": answer, "answer_path": str(answer_path)}, sys.stdout)


if __name__ == "__main__":
    main()
