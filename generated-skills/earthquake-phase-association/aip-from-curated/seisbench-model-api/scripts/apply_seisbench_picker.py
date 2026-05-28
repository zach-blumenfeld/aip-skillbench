# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy"]
# # obspy and seisbench are imported lazily by `run`; add them when you actually
# # apply a model:  uv run --with obspy --with seisbench apply_seisbench_picker.py run ...
# ///
"""Apply a pretrained SeisBench picker to an ObsPy stream and emit a pick table.

This is the runnable bridge between an ObsPy `Stream` and a SeisBench
`WaveformModel`. It encodes the two pieces of the picking step that are exact,
input-independent computation (and therefore belong in code, not prose):

  1. Tiny-amplitude rescale (a numeric threshold).
     SeisBench normalizes internally with `(x - mean) / (std + epsilon)`. When a
     trace's amplitude scale is <= 1e-10, that epsilon dominates the denominator
     and flattens the signal. The fix from the skill's Best Practices is to
     multiply the trace by a large factor (1e10) *before* normalization / before
     passing it to the model. `rescale_if_tiny` applies exactly that rule.

  2. Pick extraction (a fixed field mapping).
     `model.classify(stream).picks` is a list of pick objects; every pick exposes
     `trace_id`, `peak_time`, `peak_value`, and `phase`. `picks_to_records` maps
     those to the standard pick-table columns (`id`, `timestamp`, `prob`, `type`)
     that a downstream associator (e.g. GaMMA) expects. Phase is lower-cased.

Usage:
    # full pipeline (needs obspy + seisbench installed):
    uv run --with obspy --with seisbench apply_seisbench_picker.py run \
        --stream /root/data/wave.mseed \
        --model PhaseNet --weights instance \
        --batch-size 256 --out /root/picks.csv

    # offline check of the deterministic logic (numpy only):
    uv run apply_seisbench_picker.py --self-test

Exit codes: 0 on success / all self-tests pass; 1 on failure.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

# Amplitude scale at or below which SeisBench's epsilon normalization risks
# destroying the signal; rescale by RESCALE_FACTOR before normalizing.
TINY_AMPLITUDE = 1e-10
RESCALE_FACTOR = 1e10

# Default columns of the emitted pick table (downstream-associator friendly).
PICK_COLUMNS = ("id", "timestamp", "prob", "type")


# ---------------------------------------------------------------------------
# Deterministic, dependency-light logic (numpy only) — unit-testable offline.
# ---------------------------------------------------------------------------

def trace_scale(data: np.ndarray) -> float:
    """Amplitude scale of a 1-D trace: max absolute sample value."""
    data = np.asarray(data, dtype=np.float64)
    if data.size == 0:
        return 0.0
    return float(np.max(np.abs(data)))


def rescale_if_tiny(
    data: np.ndarray,
    floor: float = TINY_AMPLITUDE,
    factor: float = RESCALE_FACTOR,
) -> tuple[np.ndarray, bool]:
    """Multiply by `factor` when the trace scale is positive but <= `floor`.

    Returns (possibly-rescaled copy, was_rescaled). A scale of exactly 0 (a flat
    trace) is left untouched — multiplying zeros changes nothing and there is no
    signal to protect.
    """
    arr = np.asarray(data, dtype=np.float64).copy()
    scale = trace_scale(arr)
    if 0.0 < scale <= floor:
        return arr * factor, True
    return arr, False


def normalize(data: np.ndarray, epsilon: float = 1e-10) -> np.ndarray:
    """SeisBench-style demean + std normalization: (x - mean) / (std + epsilon).

    Provided so callers can normalize explicitly (the skill recommends doing so
    rather than relying solely on the model's internal normalization). Apply
    AFTER `rescale_if_tiny`, never before.
    """
    arr = np.asarray(data, dtype=np.float64)
    return (arr - arr.mean()) / (arr.std() + epsilon)


def picks_to_records(picks) -> list[dict]:
    """Map SeisBench pick objects to standard pick-table rows.

    Each pick must expose `trace_id`, `peak_time`, `peak_value`, `phase`.
    `peak_time` is a UTCDateTime-like object; `.datetime` is used when present so
    the timestamp is a plain `datetime`. Phase is lower-cased ("p"/"s").
    """
    records = []
    for p in picks:
        peak_time = getattr(p, "peak_time")
        timestamp = getattr(peak_time, "datetime", peak_time)
        records.append(
            {
                "id": p.trace_id,
                "timestamp": timestamp,
                "prob": p.peak_value,
                "type": str(p.phase).lower(),
            }
        )
    return records


# ---------------------------------------------------------------------------
# Full pipeline — lazily imports obspy + seisbench so the module imports (and
# self-tests) without the heavy stack present.
# ---------------------------------------------------------------------------

def rescale_stream(stream) -> int:
    """In place: rescale every tiny-amplitude trace in an ObsPy stream.

    Returns the count of traces that were rescaled.
    """
    rescaled = 0
    for tr in stream:
        new_data, did = rescale_if_tiny(tr.data)
        if did:
            tr.data = new_data.astype(tr.data.dtype, copy=False)
            rescaled += 1
    return rescaled


def apply_picker(
    stream_path: str,
    model_name: str = "PhaseNet",
    weights: str = "instance",
    batch_size: int = 256,
    rescale: bool = True,
    out_csv: str | None = None,
):
    """Load a stream, optionally rescale tiny traces, classify, return a pick DataFrame."""
    import obspy
    import pandas as pd
    import seisbench.models as sbm

    stream = obspy.read(stream_path)
    print(f"# traces in stream: {len(stream)}")

    if rescale:
        n = rescale_stream(stream)
        if n:
            print(f"rescaled {n} tiny-amplitude trace(s) by {RESCALE_FACTOR:g}")

    model_cls = getattr(sbm, model_name)
    print(f"available weights for {model_name}: {model_cls.list_pretrained()}")
    model = model_cls.from_pretrained(weights)
    # Move to GPU when one is available; harmless on CPU-only hosts.
    try:
        model.to_preferred_device(verbose=True)
    except AttributeError:
        pass

    picks = model.classify(stream, batch_size=batch_size).picks
    print(f"# picks: {len(picks)}")

    df = pd.DataFrame(picks_to_records(picks), columns=list(PICK_COLUMNS))
    if out_csv:
        df.to_csv(out_csv, index=False)
        print(f"wrote {len(df)} picks to {out_csv}")
    return df


# ---------------------------------------------------------------------------
# Offline self-test of the deterministic logic.
# ---------------------------------------------------------------------------

class _MockPick:
    def __init__(self, trace_id, datetime_str, prob, phase):
        self.trace_id = trace_id
        self.peak_time = type("T", (), {"datetime": datetime_str})()
        self.peak_value = prob
        self.phase = phase


def _self_test() -> int:
    failures = []

    # 1. tiny trace is rescaled; its shape/relative structure is preserved.
    tiny = np.array([1e-11, -2e-11, 5e-12], dtype=np.float64)
    out, did = rescale_if_tiny(tiny)
    if not did:
        failures.append("tiny trace (scale 2e-11 <= 1e-10) was NOT rescaled")
    if did and not np.allclose(out, tiny * RESCALE_FACTOR):
        failures.append("rescale did not multiply by the expected factor")

    # 2. normal-scale trace is left untouched.
    normal = np.array([1.0, -3.0, 2.5], dtype=np.float64)
    out2, did2 = rescale_if_tiny(normal)
    if did2:
        failures.append("normal-scale trace was rescaled but should not have been")
    if not np.array_equal(out2, normal):
        failures.append("normal-scale trace data was modified")

    # 3. exactly-zero (flat) trace is left untouched.
    flat = np.zeros(8, dtype=np.float64)
    _, did3 = rescale_if_tiny(flat)
    if did3:
        failures.append("flat (all-zero) trace was rescaled — nothing to protect")

    # 4. boundary: scale exactly at the floor (1e-10) IS rescaled (<=).
    at_floor = np.array([1e-10, -1e-10], dtype=np.float64)
    _, did4 = rescale_if_tiny(at_floor)
    if not did4:
        failures.append("trace at the 1e-10 floor was not rescaled (rule is <=)")

    # 5. normalize is demeaned and unit-ish scale.
    norm = normalize(np.array([10.0, 20.0, 30.0]))
    if abs(float(norm.mean())) > 1e-9:
        failures.append("normalize output is not mean-centered")

    # 6. pick extraction maps fields and lower-cases phase.
    recs = picks_to_records(
        [
            _MockPick("CI.CCC..", "2019-07-04T19:00:06", 0.94, "P"),
            _MockPick("CI.WBM..", "2019-07-04T19:00:09", 0.71, "S"),
        ]
    )
    expected = [
        {"id": "CI.CCC..", "timestamp": "2019-07-04T19:00:06", "prob": 0.94, "type": "p"},
        {"id": "CI.WBM..", "timestamp": "2019-07-04T19:00:09", "prob": 0.71, "type": "s"},
    ]
    if recs != expected:
        failures.append(f"picks_to_records mismatch: {recs}")

    if failures:
        print("SELF-TEST FAILURES:")
        for f in failures:
            print(f"  !! {f}")
        return 1
    print("self-test OK: rescale threshold, normalize, and pick extraction all pass")
    return 0


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="Run offline checks of the deterministic logic and exit.")
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Apply a picker to a stream and emit a pick table.")
    run.add_argument("--stream", required=True, help="Path to an ObsPy-readable waveform file (e.g. MSEED).")
    run.add_argument("--model", default="PhaseNet", help="SeisBench model class name (e.g. PhaseNet, EQTransformer, GPD).")
    run.add_argument("--weights", default="instance", help="Pretrained weights name (see Model.list_pretrained()).")
    run.add_argument("--batch-size", type=int, default=256, help="Batch size for classify/annotate.")
    run.add_argument("--no-rescale", action="store_true", help="Skip the tiny-amplitude rescale step.")
    run.add_argument("--out", default=None, help="Write the pick table to this CSV path.")

    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "run":
        df = apply_picker(
            stream_path=args.stream,
            model_name=args.model,
            weights=args.weights,
            batch_size=args.batch_size,
            rescale=not args.no_rescale,
            out_csv=args.out,
        )
        if args.out is None:
            print(df.to_string(index=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
