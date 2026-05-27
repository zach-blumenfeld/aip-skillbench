#!/usr/bin/env python3
"""
process_video.py — remove the unnecessary opening and long silences from a
teaching video and emit the required compression_report.json.

Usage:
    python process_video.py \
        --input data/input_video.mp4 \
        --output compressed_video.mp4 \
        --report compression_report.json

Strategy:
1. Probe the input duration with ffprobe.
2. Detect long silences (>= --silence-min seconds, below --silence-db) using
   ffmpeg's `silencedetect` audio filter.
3. Detect a static / frozen opening using ffmpeg's `freezedetect` video
   filter — only the freeze block that starts at or very near t=0 is treated
   as "opening", everything else is left alone (a teaching demo can legitimately
   show a still slide mid-lecture).
4. Merge overlapping removal intervals, build complementary keep intervals.
5. Re-encode kept intervals as a single mp4 with `-filter_complex` trim+concat.
6. Write compression_report.json with the schema from the task instruction.

The script depends only on `ffmpeg`/`ffprobe` being on PATH and Python 3.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

Interval = Tuple[float, float]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def ffprobe_duration(path: Path) -> float:
    r = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit(f"ffprobe failed on {path}: {r.stderr.strip()}")
    return float(r.stdout.strip())


def detect_silences(
    path: Path,
    noise_db: str,
    min_dur: float,
    file_duration: float,
) -> List[Interval]:
    """Return [(start, end), ...] of silence intervals."""
    r = run([
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(path),
        "-af", f"silencedetect=noise={noise_db}:d={min_dur}",
        "-f", "null", "-",
    ])
    text = r.stderr  # ffmpeg writes filter info to stderr
    silences: List[Interval] = []
    current_start: float | None = None
    for m in re.finditer(r"silence_(start|end):\s*(-?[0-9.]+)", text):
        kind, val = m.group(1), float(m.group(2))
        if kind == "start":
            current_start = max(0.0, val)
        else:  # end
            if current_start is not None:
                silences.append((current_start, val))
                current_start = None
    # silencedetect omits silence_end if the file ends in silence.
    if current_start is not None:
        silences.append((current_start, file_duration))
    return silences


def detect_opening_freeze(
    path: Path,
    freeze_noise: str = "0.003",
    min_dur: float = 1.0,
    start_tolerance: float = 1.0,
) -> float:
    """Return the timestamp at which the opening freeze ends, or 0.0 if none.

    Only counts freezes that begin within `start_tolerance` seconds of t=0 so a
    static slide later in the lecture isn't mistakenly removed.
    """
    r = run([
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(path),
        "-vf", f"freezedetect=n={freeze_noise}:d={min_dur}",
        "-map", "0:v:0",
        "-f", "null", "-",
    ])
    text = r.stderr
    opening_end = 0.0
    current_start: float | None = None
    for m in re.finditer(r"freeze_(start|end|duration):\s*(-?[0-9.]+)", text):
        kind, val = m.group(1), float(m.group(2))
        if kind == "start":
            current_start = val
        elif kind == "end":
            if current_start is not None and current_start <= start_tolerance:
                opening_end = max(opening_end, val)
            current_start = None
    return opening_end


def merge_intervals(intervals: List[Interval]) -> List[Interval]:
    if not intervals:
        return []
    intervals = sorted((max(0.0, s), e) for s, e in intervals if e > s)
    merged: List[list] = [list(intervals[0])]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(a, b) for a, b in merged]


def complement(duration: float, removes: List[Interval]) -> List[Interval]:
    """Return the keep intervals — duration minus removes."""
    keeps: List[Interval] = []
    cursor = 0.0
    for s, e in removes:
        s = max(0.0, min(duration, s))
        e = max(0.0, min(duration, e))
        if s > cursor:
            keeps.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        keeps.append((cursor, duration))
    # Drop slivers (sub-frame intervals) that would confuse the concat filter.
    return [(s, e) for s, e in keeps if (e - s) > 0.05]


def cut_and_concat(in_path: Path, keeps: List[Interval], out_path: Path) -> None:
    if not keeps:
        raise SystemExit("No keep segments — refusing to produce an empty video.")
    parts: list[str] = []
    n = len(keeps)
    for i, (s, e) in enumerate(keeps):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
    labels = "".join(f"[v{i}][a{i}]" for i in range(n))
    parts.append(f"{labels}concat=n={n}:v=1:a=1[outv][outa]")
    filter_complex = ";".join(parts)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(in_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("ffmpeg failed to produce output video.")


def round3(x: float) -> float:
    return round(float(x), 3)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Path to the input video.")
    p.add_argument("--output", default="compressed_video.mp4",
                   help="Path for the compressed video (default: ./compressed_video.mp4).")
    p.add_argument("--report", default="compression_report.json",
                   help="Path for the JSON report (default: ./compression_report.json).")
    p.add_argument("--silence-db", default="-30dB",
                   help="Audio level treated as silence (default: -30dB).")
    p.add_argument("--silence-min", type=float, default=2.0,
                   help="Minimum silence duration in seconds (default: 2.0).")
    p.add_argument("--freeze-noise", default="0.003",
                   help="freezedetect noise tolerance — smaller is stricter (default: 0.003).")
    p.add_argument("--freeze-min", type=float, default=1.0,
                   help="Minimum opening-freeze duration in seconds (default: 1.0).")
    p.add_argument("--skip-opening", action="store_true",
                   help="Disable opening-freeze detection.")
    p.add_argument("--verbose", action="store_true",
                   help="Print detected intervals before cutting.")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"Input file not found: {in_path}")

    duration = ffprobe_duration(in_path)
    silences = detect_silences(in_path, args.silence_db, args.silence_min, duration)

    opening_end = 0.0
    if not args.skip_opening:
        opening_end = detect_opening_freeze(
            in_path,
            freeze_noise=args.freeze_noise,
            min_dur=args.freeze_min,
        )

    removes: List[Interval] = list(silences)
    if opening_end > 0.0:
        removes.append((0.0, opening_end))

    removes = merge_intervals(removes)
    keeps = complement(duration, removes)

    if args.verbose:
        print(f"original duration: {duration:.3f}s", file=sys.stderr)
        print(f"opening freeze end: {opening_end:.3f}s", file=sys.stderr)
        print(f"silences: {silences}", file=sys.stderr)
        print(f"removes (merged): {removes}", file=sys.stderr)
        print(f"keeps: {keeps}", file=sys.stderr)

    cut_and_concat(in_path, keeps, Path(args.output))
    out_duration = ffprobe_duration(Path(args.output))
    removed = max(0.0, duration - out_duration)

    report = {
        "original_duration_seconds": round3(duration),
        "compressed_duration_seconds": round3(out_duration),
        "removed_duration_seconds": round3(removed),
        "compression_percentage": round3((removed / duration) * 100.0) if duration > 0 else 0.0,
        "segments_removed": [
            {"start": round3(s), "end": round3(e), "duration": round3(e - s)}
            for s, e in removes
        ],
    }
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output} and {args.report}")
    print(
        f"Original: {duration:.2f}s -> Compressed: {out_duration:.2f}s "
        f"({report['compression_percentage']:.1f}% removed)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
