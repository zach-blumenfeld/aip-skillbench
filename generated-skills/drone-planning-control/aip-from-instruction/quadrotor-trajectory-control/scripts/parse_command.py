#!/usr/bin/env python3
"""Parse the four supported natural-language commands into a structured dict.

Supported forms (case-insensitive, numbers may be int or float):
  - "Take off to <h> m height in <t> seconds"
  - "Hover at <h> m height for <t> seconds"
  - "Land from <h> m height in <t> seconds"
  - "Fly from (<x>,<y>,<z>) to (<x'>,<y'>,<z'>) in <t> seconds"

Returns a dict with keys:
  mode:   "takeoff" | "hover" | "land" | "fly"
  start:  (x0, y0, z0)  numpy array length 3
  end:    (x1, y1, z1)  numpy array length 3
  T:      float duration in seconds
  raw:    original text

Usage:
    from parse_command import parse_command
    cmd = parse_command(open("commands/001.txt").read())
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

NUM = r"[-+]?\d+(?:\.\d+)?"

PATTERNS = {
    "takeoff": re.compile(
        rf"take\s*off\s+to\s+({NUM})\s*m\s*(?:height\s+)?in\s+({NUM})\s*seconds?",
        re.IGNORECASE,
    ),
    "hover": re.compile(
        rf"hover\s+at\s+({NUM})\s*m\s*(?:height\s+)?for\s+({NUM})\s*seconds?",
        re.IGNORECASE,
    ),
    "land": re.compile(
        rf"land\s+from\s+({NUM})\s*m\s*(?:height\s+)?in\s+({NUM})\s*seconds?",
        re.IGNORECASE,
    ),
    "fly": re.compile(
        rf"fly\s+from\s*\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*\)"
        rf"\s+to\s*\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*\)"
        rf"\s+in\s+({NUM})\s*seconds?",
        re.IGNORECASE,
    ),
}


def parse_command(text: str) -> dict:
    text = text.strip()
    for mode, pat in PATTERNS.items():
        m = pat.search(text)
        if not m:
            continue
        if mode == "takeoff":
            h, T = float(m.group(1)), float(m.group(2))
            return dict(
                mode=mode,
                start=np.array([0.0, 0.0, 0.0]),
                end=np.array([0.0, 0.0, h]),
                T=T,
                raw=text,
            )
        if mode == "hover":
            h, T = float(m.group(1)), float(m.group(2))
            return dict(
                mode=mode,
                start=np.array([0.0, 0.0, h]),
                end=np.array([0.0, 0.0, h]),
                T=T,
                raw=text,
            )
        if mode == "land":
            h, T = float(m.group(1)), float(m.group(2))
            return dict(
                mode=mode,
                start=np.array([0.0, 0.0, h]),
                end=np.array([0.0, 0.0, 0.0]),
                T=T,
                raw=text,
            )
        if mode == "fly":
            g = list(map(float, m.groups()))
            return dict(
                mode=mode,
                start=np.array(g[0:3]),
                end=np.array(g[3:6]),
                T=g[6],
                raw=text,
            )
    raise ValueError(f"Unrecognized command: {text!r}")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        cmd = parse_command(Path(path).read_text())
        print(path, "->", cmd["mode"], "T=", cmd["T"],
              "start=", cmd["start"].tolist(), "end=", cmd["end"].tolist())
