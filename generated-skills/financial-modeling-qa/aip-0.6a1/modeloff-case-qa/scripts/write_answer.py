"""Normalize the final answer to the requested form and write it to the answer file.

stdin: {"state": {"<x>_answer": str, "answer_path": str, "answer_format": str}, ...}
stdout: {"<x>_answer_written": str}   (x = dice or model, whichever answer key was given)

answer_format: integer | decimal | text. Numbers lose thousands separators, currency and
unit symbols, and a trailing '.0'; parentheses become a minus sign. Text is written trimmed.
"""
import json
import re
import sys


def normalize(raw, form):
    s = str(raw).strip()
    if form == "text":
        return s
    t = s.replace(",", "").replace("$", "").replace("£", "").replace("€", "").strip()
    pct = t.endswith("%")
    t = t.rstrip("%").strip()
    if re.fullmatch(r"\(\s*[-+]?\d*\.?\d+\s*\)", t):
        t = "-" + t.strip("() ")
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", t)
    if not m:
        raise SystemExit(f"answer_format is {form} but the answer has no number: {raw!r}")
    x = float(m.group(0))
    if form == "integer":
        if abs(x - round(x)) > 1e-9:
            raise SystemExit(f"answer_format is integer but the answer is {x}; recheck the computation or the format")
        return str(int(round(x)))
    out = repr(x) if not x.is_integer() else str(int(x))
    return out + ("%" if pct else "")


def main():
    state = json.load(sys.stdin)["state"]
    keys = [k for k in state if k.endswith("_answer")]
    if len(keys) != 1:
        raise SystemExit(f"expected exactly one *_answer key in state, got {keys}")
    key = keys[0]
    text = normalize(state[key], state.get("answer_format", "text"))
    with open(state["answer_path"], "w") as f:
        f.write(text + "\n")
    json.dump({f"{key}_written": text}, sys.stdout)


if __name__ == "__main__":
    main()
