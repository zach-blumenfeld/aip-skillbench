"""Natural-language flight commands -> (4 x n) waypoints, (n,) times, (n-1) modes."""
import re

import numpy as np

_NUM = r"([-+]?\d*\.?\d+)"
_M = r"\s*(?:m|meters?|metres?)\b"
_S = r"\s*(?:s|sec|secs|seconds?)\b"
_PT = r"\(\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*\)"

PATTERNS = {
    "takeoff": re.compile(r"take\s*-?\s*off\s+to\s+" + _NUM + _M + r"(?:\s+height)?\s+in\s+" + _NUM + _S, re.IGNORECASE),
    "hover": re.compile(r"hover\s+at\s+" + _NUM + _M + r"(?:\s+height)?\s+for\s+" + _NUM + _S, re.IGNORECASE),
    "fly": re.compile(r"fly\s+from\s*" + _PT + r"\s*to\s*" + _PT + r"\s*in\s+" + _NUM + _S, re.IGNORECASE),
    "land": re.compile(r"land\s+from\s+" + _NUM + _M + r"(?:\s+height)?\s+in\s+" + _NUM + _S, re.IGNORECASE),
}


class FlightPlanParser:
    """Stateful parser: each command appends its END waypoint, arrival time and mode."""

    def __init__(self, start=(0.0, 0.0, 0.0), yaw=0.0):
        self.position = [float(start[0]), float(start[1]), float(start[2]), float(yaw)]
        self.time = 0.0
        self.waypoints = []
        self.times = []
        self.modes = []

    def _ensure_start(self, start_xyz=None):
        # The first command fixes where the vehicle starts: (0,0,0) for takeoff, the
        # stated height for hover/land, the `from` point for fly.
        if not self.waypoints:
            if start_xyz is not None:
                self.position[:3] = [float(v) for v in start_xyz]
            self.waypoints.append(list(self.position))
            self.times.append(0.0)

    def _push(self, end_xyz, duration, mode):
        if duration <= 0:
            raise ValueError(f"{mode}: duration must be > 0, got {duration}")
        self.position[:3] = [float(v) for v in end_xyz]
        self.time += float(duration)
        self.waypoints.append(list(self.position))  # copy, never the shared list
        self.times.append(self.time)
        self.modes.append(mode)

    def takeoff(self, h, t):
        self._ensure_start()
        x, y, _ = self.position[:3]
        self._push((x, y, h), t, "takeoff")

    def hover(self, h, t):
        x, y = (self.position[0], self.position[1])
        self._ensure_start((x, y, h))
        self._push((x, y, h), t, "hover")

    def fly(self, x0, y0, z0, x1, y1, z1, t):
        self._ensure_start((x0, y0, z0))
        self._push((x1, y1, z1), t, "fly")

    def land(self, h, t):
        x, y = (self.position[0], self.position[1])
        self._ensure_start((x, y, h))
        self._push((self.position[0], self.position[1], 0.0), t, "land")

    def feed(self, line):
        line = line.strip()
        if not line:
            return
        for mode, pat in PATTERNS.items():
            m = pat.search(line)
            if m:
                vals = [float(v) for v in m.groups()]
                getattr(self, mode)(*vals)
                return
        raise ValueError(f"Unrecognised flight command: {line!r}")

    def result(self):
        if not self.waypoints:
            raise ValueError("No flight commands found")
        return np.array(self.waypoints, dtype=float).T, np.array(self.times, dtype=float), list(self.modes)


def parse_flight_plan(text):
    """Return (waypoints (4 x n), waypoint_times (n,), modes list of n-1 strings)."""
    parser = FlightPlanParser()
    for line in text.splitlines():
        parser.feed(line)
    return parser.result()
