"""Parse a single-line natural-language drone command.

Supported templates (case-insensitive, flexible whitespace):
  - Take off to <h> m height in <t> seconds
  - Hover at <h> m height for <t> seconds
  - Land from <h> m height in <t> seconds
  - Fly from (<x>,<y>,<z>) to (<x'>,<y'>,<z'>) in <t> seconds
"""
from __future__ import annotations

import json
import re
import sys

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"

PATTERNS = {
    "takeoff": re.compile(
        rf"take\s*off\s*to\s*({NUM})\s*m(?:eter)?s?\s*(?:height\s*)?in\s*({NUM})\s*s(?:ec(?:ond)?s?)?",
        re.I,
    ),
    "hover": re.compile(
        rf"hover\s*at\s*({NUM})\s*m(?:eter)?s?\s*(?:height\s*)?for\s*({NUM})\s*s(?:ec(?:ond)?s?)?",
        re.I,
    ),
    "land": re.compile(
        rf"land\s*from\s*({NUM})\s*m(?:eter)?s?\s*(?:height\s*)?in\s*({NUM})\s*s(?:ec(?:ond)?s?)?",
        re.I,
    ),
    "fly": re.compile(
        rf"fly\s*from\s*\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*\)\s*"
        rf"to\s*\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*\)\s*in\s*({NUM})\s*s(?:ec(?:ond)?s?)?",
        re.I,
    ),
}


def parse(text: str) -> dict:
    text = text.strip()
    for mode, pat in PATTERNS.items():
        m = pat.search(text)
        if not m:
            continue
        if mode in ("takeoff", "hover", "land"):
            h = float(m.group(1))
            t = float(m.group(2))
            return {"mode": mode, "h": h, "t": t, "raw": text}
        g = [float(x) for x in m.groups()]
        return {"mode": "fly", "p0": g[0:3], "p1": g[3:6], "t": g[6], "raw": text}
    raise ValueError(f"Unrecognized command: {text!r}")


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        print(json.dumps(parse(f.read()), indent=2))
