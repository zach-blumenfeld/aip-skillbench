#!/usr/bin/env python3
"""Detect removable segments (opening + long pauses) in a teaching video.

Runs ffmpeg's `silencedetect` (audio pauses) and `freezedetect` (static
opening frames), merges the hits into a removal plan, and writes the
complement (the teaching content to keep) to an analysis JSON.

The pure logic (parsing, merging, complement) is split from the ffmpeg
calls so it can be unit-tested without ffmpeg installed.

Requires: ffmpeg + ffprobe on PATH.

Usage:
  python detect_segments.py --input data/input_video.mp4 --out analysis.json
"""
import argparse
import json
import re
import shutil
import subprocess
import sys


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            die(f"`{tool}` not found on PATH. Install ffmpeg before running.")


def probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    if out.returncode != 0 or not out.stdout.strip():
        die(f"ffprobe could not read duration of {path}: {out.stderr.strip()}")
    try:
        return float(out.stdout.strip())
    except ValueError:
        die(f"ffprobe returned a non-numeric duration: {out.stdout!r}")


def has_audio_stream(path: str) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


def run_silencedetect(path: str, noise_db: float, min_dur: float) -> str:
    """Return ffmpeg stderr text from a silencedetect pass."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return proc.stderr


def run_freezedetect(path: str, noise_db: float, min_dur: float) -> str:
    """Return ffmpeg stderr text from a freezedetect pass."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
         "-vf", f"freezedetect=n={noise_db}dB:d={min_dur}",
         "-map", "0:v:0", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return proc.stderr


# ---- pure parsing / interval logic (unit-testable, no ffmpeg) -------------

def parse_silences(stderr: str, duration: float) -> list[dict]:
    """Parse silence_start / silence_end pairs from silencedetect stderr."""
    starts = [float(m) for m in re.findall(r"silence_start:\s*([0-9.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([0-9.]+)", stderr)]
    segs = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else duration  # trailing silence runs to EOF
        if e > s:
            segs.append({"start": s, "end": e})
    return segs


def parse_freezes(stderr: str, duration: float) -> list[dict]:
    """Parse freeze_start / freeze_end pairs from freezedetect stderr."""
    starts = [float(m) for m in re.findall(r"freeze_start:\s*([0-9.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"freeze_end:\s*([0-9.]+)", stderr)]
    segs = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else duration
        if e > s:
            segs.append({"start": s, "end": e})
    return segs


def pick_opening(freezes: list[dict], max_start: float) -> dict | None:
    """The opening is the first freeze that begins at/near the video start.

    Mid-video freezes (a presenter holding still while talking) are NOT the
    opening and must be kept, so only a freeze whose start <= max_start counts.
    """
    if not freezes:
        return None
    first = min(freezes, key=lambda x: x["start"])
    if first["start"] <= max_start:
        return {"start": 0.0, "end": first["end"]}
    return None  # earliest freeze starts too late to be the opening


def merge_intervals(intervals: list[dict], gap: float) -> list[dict]:
    """Sort and merge overlapping/adjacent intervals (within `gap` seconds)."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda x: x["start"])
    merged = [dict(ordered[0])]
    for cur in ordered[1:]:
        last = merged[-1]
        if cur["start"] <= last["end"] + gap:
            last["end"] = max(last["end"], cur["end"])
        else:
            merged.append(dict(cur))
    return merged


def apply_pad(segs: list[dict], pad: float) -> list[dict]:
    """Shrink silence removals by `pad` on both ends so speech is not clipped.

    Opening segments are left untouched — we want the whole opening gone, and
    freeze bounds are already precise.
    """
    out = []
    for s in segs:
        if s.get("reason") == "opening" or pad <= 0:
            out.append(dict(s))
            continue
        a, b = s["start"] + pad, s["end"] - pad
        if b - a > 0.05:
            seg = dict(s)
            seg["start"], seg["end"] = round(a, 3), round(b, 3)
            out.append(seg)
    return out


def finalize(merged: list[dict], duration: float, min_keep: float,
             opening_end: float) -> tuple[list[dict], list[dict]]:
    """Turn merged removals into keep+removal lists that EXACTLY partition
    [0, duration]. Keep slivers shorter than `min_keep` are absorbed into the
    removals (cut) so no time falls into neither bucket — this is what keeps
    the report math `original == compressed + removed` exact.
    """
    keeps, cursor = [], 0.0
    for r in sorted(merged, key=lambda x: x["start"]):
        if r["start"] - cursor >= min_keep:
            keeps.append({"start": round(cursor, 3), "end": round(r["start"], 3)})
        cursor = max(cursor, r["end"])
    if duration - cursor >= min_keep:
        keeps.append({"start": round(cursor, 3), "end": round(duration, 3)})

    removals, cur = [], 0.0
    for k in keeps:
        if k["start"] - cur > 1e-6:
            removals.append(_removal(cur, k["start"], opening_end))
        cur = k["end"]
    if duration - cur > 1e-6:
        removals.append(_removal(cur, duration, opening_end))
    return keeps, removals


def _removal(start: float, end: float, opening_end: float) -> dict:
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "reason": "opening" if start < opening_end else "silence",
    }


def build_plan(duration, silences, freezes, *, min_silence, opening_max_start,
               pad, gap, min_keep) -> dict:
    removals = []
    opening = pick_opening(freezes, opening_max_start)
    opening_end = opening["end"] if opening else 0.0
    if opening:
        removals.append({**opening, "reason": "opening"})
    for s in silences:
        if s["end"] - s["start"] >= min_silence:
            removals.append({**s, "reason": "silence"})

    removals = apply_pad(removals, pad)
    for r in removals:
        r["start"] = max(0.0, r["start"])
        r["end"] = min(duration, r["end"])
    # Merge across gaps smaller than a keepable sliver, so tiny teaching
    # fragments between cuts are absorbed rather than orphaned.
    merged = merge_intervals(removals, max(gap, min_keep))
    merged = [m for m in merged if m["end"] > m["start"]]

    keeps, final_removals = finalize(merged, duration, min_keep, opening_end)
    removed_total = round(sum(r["duration"] for r in final_removals), 3)
    return {
        "removal_segments": final_removals,
        "keep_segments": keeps,
        "removed_duration_seconds": removed_total,
        "compression_percentage_preview": round(100 * removed_total / duration, 2) if duration else 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="analysis.json")
    ap.add_argument("--silence-noise-db", type=float, default=-30.0,
                    help="silencedetect noise floor in dB (less negative = stricter)")
    ap.add_argument("--min-silence", type=float, default=2.0,
                    help="minimum pause length to remove, seconds")
    ap.add_argument("--freeze-noise-db", type=float, default=-60.0,
                    help="freezedetect per-pixel noise tolerance in dB")
    ap.add_argument("--min-freeze", type=float, default=2.0,
                    help="minimum frozen duration to count, seconds")
    ap.add_argument("--opening-max-start", type=float, default=3.0,
                    help="a leading freeze starting within this many seconds is the opening")
    ap.add_argument("--keep-pad", type=float, default=0.1,
                    help="seconds of audio kept around each cut so speech is not clipped")
    ap.add_argument("--merge-gap", type=float, default=0.3,
                    help="removals closer than this are merged")
    ap.add_argument("--min-keep", type=float, default=0.3,
                    help="keep segments shorter than this are discarded")
    args = ap.parse_args()

    require_tools()
    duration = probe_duration(args.input)
    audio = has_audio_stream(args.input)

    silences = parse_silences(
        run_silencedetect(args.input, args.silence_noise_db, args.min_silence), duration
    ) if audio else []
    freezes = parse_freezes(
        run_freezedetect(args.input, args.freeze_noise_db, args.min_freeze), duration
    )

    plan = build_plan(
        duration, silences, freezes,
        min_silence=args.min_silence, opening_max_start=args.opening_max_start,
        pad=args.keep_pad, gap=args.merge_gap, min_keep=args.min_keep,
    )

    analysis = {
        "input": args.input,
        "original_duration_seconds": round(duration, 3),
        "has_audio": audio,
        "params": {
            "silence_noise_db": args.silence_noise_db,
            "min_silence": args.min_silence,
            "freeze_noise_db": args.freeze_noise_db,
            "min_freeze": args.min_freeze,
            "opening_max_start": args.opening_max_start,
            "keep_pad": args.keep_pad,
        },
        "raw_silences": silences,
        "raw_freezes": freezes,
        **plan,
    }
    with open(args.out, "w") as fh:
        json.dump(analysis, fh, indent=2)

    print(f"Detected {len(plan['removal_segments'])} removal segment(s), "
          f"keeping {len(plan['keep_segments'])} segment(s). "
          f"Preview compression: {plan['compression_percentage_preview']}% "
          f"({plan['removed_duration_seconds']}s of {round(duration,1)}s). "
          f"Wrote {args.out}.")


if __name__ == "__main__":
    main()
