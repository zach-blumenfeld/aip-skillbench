"""Natural-language flight command -> waypoints, arrival times, segment modes.

Requires: Python >= 3.8, numpy.

    waypoints      : (4 x n) array, rows [x, y, z, yaw]
    waypoint_times : (n,)    array, arrival time of each waypoint [s]
    modes          : list of n-1 strings, one per segment ('takeoff'|'hover'|'fly'|'land')

CLI check:  python3 flight_plan_parser.py /root/commands/001.txt
"""
import re
import sys

import numpy as np

_NUM = r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
_TRIPLE = r"\(\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*\)"

PATTERNS = {
    "takeoff": re.compile(r"take\s*-?\s*off\s+to\s+" + _NUM + r"\s*m(?:eters?|etres?)?\s+(?:height|altitude)?\s*in\s+" + _NUM + r"\s*s", re.IGNORECASE),
    "hover": re.compile(r"hover\s+at\s+" + _NUM + r"\s*m(?:eters?|etres?)?\s+(?:height|altitude)?\s*for\s+" + _NUM + r"\s*s", re.IGNORECASE),
    "land": re.compile(r"land\s+from\s+" + _NUM + r"\s*m(?:eters?|etres?)?\s+(?:height|altitude)?\s*in\s+" + _NUM + r"\s*s", re.IGNORECASE),
    "fly": re.compile(r"fly\s+from\s+" + _TRIPLE + r"\s+to\s+" + _TRIPLE + r"\s+in\s+" + _NUM + r"\s*s", re.IGNORECASE),
}


class FlightPlanParser:
    """Stateful: accumulates waypoints/times/modes one command line at a time."""

    def __init__(self):
        self.pos = [0.0, 0.0, 0.0, 0.0]  # x, y, z, yaw
        self.t = 0.0
        self.waypoints = []
        self.times = []
        self.modes = []

    def _start(self, start_pos):
        # First command: insert the start waypoint at t=0. The start is where the
        # command itself begins (ground for takeoff, (0,0,h) for hover/land, the
        # "from" point for fly) so hover/land/fly do not begin with a fake climb.
        if not self.waypoints:
            self.pos = list(start_pos)
            self.waypoints.append(list(self.pos))
            self.times.append(self.t)

    def _push(self, end_pos, duration, mode):
        if duration <= 0:
            raise ValueError(f"{mode}: duration must be > 0, got {duration}")
        self.t += duration
        self.pos = list(end_pos)
        self.waypoints.append(list(self.pos))  # copy: never share the list
        self.times.append(self.t)
        self.modes.append(mode)

    def feed(self, line):
        line = line.strip()
        if not line:
            return
        yaw = self.pos[3]
        m = PATTERNS["fly"].search(line)
        if m:
            v = [float(g) for g in m.groups()]
            self._start([v[0], v[1], v[2], yaw])
            self._push([v[3], v[4], v[5], yaw], v[6], "fly")
            return
        m = PATTERNS["takeoff"].search(line)
        if m:
            h, t = float(m.group(1)), float(m.group(2))
            x, y = (self.pos[0], self.pos[1])
            self._start([x, y, 0.0, yaw])
            self._push([self.pos[0], self.pos[1], h, yaw], t, "takeoff")
            return
        m = PATTERNS["hover"].search(line)
        if m:
            h, t = float(m.group(1)), float(m.group(2))
            self._start([self.pos[0], self.pos[1], h, yaw])
            self._push([self.pos[0], self.pos[1], h, yaw], t, "hover")
            return
        m = PATTERNS["land"].search(line)
        if m:
            h, t = float(m.group(1)), float(m.group(2))
            self._start([self.pos[0], self.pos[1], h, yaw])
            self._push([self.pos[0], self.pos[1], 0.0, yaw], t, "land")
            return
        raise ValueError(f"Unrecognised flight command: {line!r}")

    def result(self):
        if not self.modes:
            raise ValueError("No flight command found")
        return np.array(self.waypoints, dtype=float).T, np.array(self.times, dtype=float), list(self.modes)


def parse_flight_plan(text):
    """Return (waypoints (4,n), waypoint_times (n,), modes list[n-1])."""
    p = FlightPlanParser()
    for line in text.splitlines():
        p.feed(line)
    return p.result()


if __name__ == "__main__":
    for path in sys.argv[1:]:
        with open(path) as f:
            wp, wt, modes = parse_flight_plan(f.read())
        print(path, "modes=", modes, "times=", wt.tolist())
        print(np.array2string(wp, precision=3))
