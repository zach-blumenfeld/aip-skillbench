"""Flight-plan parser.

Converts natural-language flight commands into the structured form the drone
simulator's trajectory planner expects:

    waypoints      : (4, n) numpy array — rows [x, y, z, yaw]
    waypoint_times : (n,)   numpy array — arrival time of each waypoint [s]
    modes          : list[str] of length (n-1) — one mode per segment

Supported command grammar (case-insensitive):

    Take off to <h> m height in <t> seconds
    Hover at  <h> m height for <t> seconds
    Land from <h> m height in <t> seconds
    Fly from (<x>,<y>,<z>) [location] to (<x'>,<y'>,<z'>) in <t> seconds

The parser is stateful: it accumulates waypoints/times/modes across successive
command lines. On the first command it auto-inserts a starting waypoint at the
current position (default (0,0,0)) and t=0 — except for ``Fly`` whose
``from (...)`` coordinates seed the start instead.

Public entry point: :func:`parse_flight_plan`.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

import numpy as np

_PATTERNS = [
    (re.compile(
        r'take\s+off\s+to\s+([\d.]+)\s*m\s+height\s+in\s+([\d.]+)\s+seconds?',
        re.IGNORECASE), 'takeoff'),
    (re.compile(
        r'hover\s+at\s+([\d.]+)\s*m\s+height\s+for\s+([\d.]+)\s+seconds?',
        re.IGNORECASE), 'hover'),
    (re.compile(
        r'land\s+from\s+([\d.]+)\s*m\s+height\s+in\s+([\d.]+)\s+seconds?',
        re.IGNORECASE), 'land'),
    (re.compile(
        r'fly\s+from\s+\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)'
        r'\s+(?:location\s+)?to\s+\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)'
        r'\s+in\s+([\d.]+)\s+seconds?',
        re.IGNORECASE), 'fly'),
]


class FlightPlanParser:
    """Accumulate waypoints/times/modes one command at a time."""

    def __init__(self) -> None:
        self._waypoints: List[List[float]] = []
        self._times: List[float] = []
        self._modes: List[str] = []
        self._t: float = 0.0
        self._pos: List[float] = [0.0, 0.0, 0.0]

    def _ensure_start(self) -> None:
        if not self._waypoints:
            self._push(list(self._pos), self._t)

    def _push(self, pos: List[float], t: float, yaw: float = 0.0) -> None:
        self._waypoints.append([pos[0], pos[1], pos[2], yaw])
        self._times.append(t)

    def _handle_takeoff(self, m: re.Match) -> None:
        h, d = float(m.group(1)), float(m.group(2))
        self._ensure_start()
        self._t += d
        self._pos[2] = h
        self._push(list(self._pos), self._t)
        self._modes.append('takeoff')

    def _handle_hover(self, m: re.Match) -> None:
        h, d = float(m.group(1)), float(m.group(2))
        # Snap altitude before inserting the start waypoint so the segment
        # is a true hover (no implicit climb on the first command).
        self._pos[2] = h
        self._ensure_start()
        self._t += d
        self._push(list(self._pos), self._t)
        self._modes.append('hover')

    def _handle_land(self, m: re.Match) -> None:
        h, d = float(m.group(1)), float(m.group(2))
        # Start the segment at the stated descent height; end at ground.
        self._pos[2] = h
        self._ensure_start()
        self._t += d
        self._pos[2] = 0.0
        self._push(list(self._pos), self._t)
        self._modes.append('land')

    def _handle_fly(self, m: re.Match) -> None:
        x0, y0, z0 = float(m.group(1)), float(m.group(2)), float(m.group(3))
        x1, y1, z1 = float(m.group(4)), float(m.group(5)), float(m.group(6))
        d = float(m.group(7))
        # Fly seeds its own start waypoint from the `from (...)` triple
        # rather than the default (0,0,0).
        if not self._waypoints:
            self._push([x0, y0, z0], self._t)
        self._t += d
        self._pos = [x1, y1, z1]
        self._push(list(self._pos), self._t)
        self._modes.append('fly')

    _handlers = {
        'takeoff': _handle_takeoff,
        'hover': _handle_hover,
        'land': _handle_land,
        'fly': _handle_fly,
    }

    def parse(self, cmd: str) -> None:
        for pat, name in _PATTERNS:
            m = pat.match(cmd.strip())
            if m:
                self._handlers[name](self, m)
                return
        raise ValueError(f"Unrecognized command: '{cmd}'")

    def result(self) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        return (
            np.array(self._waypoints).T,
            np.array(self._times),
            list(self._modes),
        )


def parse_flight_plan(
    commands: "str | Iterable[str]",
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Parse one or more flight commands.

    Accepts either a single multi-line string (one command per line) or an
    iterable of command strings. Returns ``(waypoints, waypoint_times, modes)``.
    """
    if isinstance(commands, str):
        commands = [l.strip() for l in commands.strip().splitlines() if l.strip()]
    parser = FlightPlanParser()
    for cmd in commands:
        parser.parse(cmd)
    return parser.result()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: flight_plan_parser.py <command-file-or-text>", file=sys.stderr)
        sys.exit(2)
    arg = sys.argv[1]
    try:
        with open(arg) as f:
            text = f.read()
    except OSError:
        text = arg
    wp, wt, modes = parse_flight_plan(text)
    print("waypoints (4xn):")
    print(wp)
    print("waypoint_times:", wt.tolist())
    print("modes:", modes)
