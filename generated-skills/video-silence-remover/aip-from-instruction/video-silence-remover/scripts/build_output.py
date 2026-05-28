#!/usr/bin/env python3
"""Render the compressed video from a detection plan and write the report.

Reads analysis.json (from detect_segments.py), trims+concatenates the
keep_segments into compressed_video.mp4 with a single frame-accurate ffmpeg
pass, then writes compression_report.json and runs internal consistency
checks (exits non-zero if the math is inconsistent).

Requires: ffmpeg + ffprobe on PATH.

Usage:
  python build_output.py --input data/input_video.mp4 --analysis analysis.json \
      --video-out compressed_video.mp4 --report-out compression_report.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


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
        die(f"ffprobe could not read {path}: {out.stderr.strip()}")
    return float(out.stdout.strip())


def build_filtergraph(keeps: list[dict], audio: bool) -> str:
    """One trim+concat filter_complex covering every keep segment."""
    parts, labels = [], []
    for i, k in enumerate(keeps):
        s, e = k["start"], k["end"]
        parts.append(
            f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}];"
        )
        if audio:
            parts.append(
                f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}];"
            )
        labels.append(f"[v{i}]" + (f"[a{i}]" if audio else ""))
    n = len(keeps)
    if audio:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[outv][outa]")
    else:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=0[outv]")
    return "".join(parts)


def render(input_path, keeps, audio, video_out) -> None:
    graph = build_filtergraph(keeps, audio)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(graph)
        graph_file = fh.name
    cmd = ["ffmpeg", "-y", "-hide_banner", "-nostats", "-i", input_path,
           "-filter_complex_script", graph_file,
           "-map", "[outv]"]
    if audio:
        cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-movflags", "+faststart", video_out]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(graph_file)
    if proc.returncode != 0:
        die(f"ffmpeg render failed:\n{proc.stderr[-2000:]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--analysis", default="analysis.json")
    ap.add_argument("--video-out", default="compressed_video.mp4")
    ap.add_argument("--report-out", default="compression_report.json")
    ap.add_argument("--duration-tolerance", type=float, default=1.0,
                    help="max allowed gap between planned and rendered duration, seconds")
    args = ap.parse_args()

    require_tools()
    with open(args.analysis) as fh:
        analysis = json.load(fh)

    keeps = analysis["keep_segments"]
    removals = analysis["removal_segments"]
    if not keeps:
        die("No keep_segments in analysis — the plan would remove the whole video. "
            "Loosen thresholds in detect_segments.py and re-run.")

    original = probe_duration(args.input)
    audio = analysis.get("has_audio", True)

    render(args.input, keeps, audio, args.video_out)
    actual = probe_duration(args.video_out)

    removed_total = round(sum(r["end"] - r["start"] for r in removals), 3)
    compressed = round(sum(k["end"] - k["start"] for k in keeps), 3)
    pct = round(100 * removed_total / original, 2) if original else 0.0

    report = {
        "original_duration_seconds": round(original, 3),
        "compressed_duration_seconds": compressed,
        "removed_duration_seconds": removed_total,
        "compression_percentage": pct,
        "segments_removed": [
            {"start": round(r["start"], 3), "end": round(r["end"], 3),
             "duration": round(r["end"] - r["start"], 3)}
            for r in removals
        ],
    }

    # ---- consistency checks ------------------------------------------------
    errors = []
    if abs(original - (compressed + removed_total)) > 0.75:
        errors.append(
            f"math: original {original:.2f} != compressed {compressed:.2f} + "
            f"removed {removed_total:.2f}")
    if abs(actual - compressed) > args.duration_tolerance:
        errors.append(
            f"rendered duration {actual:.2f}s diverges from planned "
            f"{compressed:.2f}s by > {args.duration_tolerance}s")
    if not (0 <= pct < 100):
        errors.append(f"compression_percentage {pct} out of [0,100)")
    for r in report["segments_removed"]:
        if not (0 <= r["start"] < r["end"] <= original + 0.5):
            errors.append(f"bad segment bounds: {r}")
        if abs(r["duration"] - (r["end"] - r["start"])) > 0.01:
            errors.append(f"segment duration mismatch: {r}")

    with open(args.report_out, "w") as fh:
        json.dump(report, fh, indent=2)

    if errors:
        for e in errors:
            print(f"CHECK FAILED: {e}", file=sys.stderr)
        die("Consistency checks failed — review thresholds and re-run.")

    print(f"Wrote {args.video_out} ({actual:.1f}s) and {args.report_out}. "
          f"Removed {removed_total:.1f}s of {original:.1f}s "
          f"({pct}% compression), {len(removals)} segment(s).")


if __name__ == "__main__":
    main()
