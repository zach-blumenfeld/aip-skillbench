#!/usr/bin/env python3
"""Pick P and S phases from MSEED waveforms with a SeisBench deep-learning model.

Writes a picks CSV with one row per pick:

    trace_id, station, phase, time, probability

  * `station`     - "NETWORK.STATION" id used to join against stations.csv.
  * `phase`       - upper-case "P" or "S".
  * `time`        - ISO-8601 UTC, no timezone suffix (e.g. 2019-01-01T12:00:00.123456).
  * `probability` - model confidence at the pick peak (0-1).

The picking model and detection thresholds are the main accuracy knobs.
Lower thresholds -> more picks -> higher recall for the downstream
associator (and more false picks, which the associator mostly rejects).

Usage:
    python pick_phases.py --waveform /root/data/wave.mseed \
        --stations /root/data/stations.csv --out picks.csv \
        [--model phasenet] [--weights instance] \
        [--p-threshold 0.2] [--s-threshold 0.2] [--batch-size 256]
"""
import argparse
import sys

import pandas as pd

# Pretrained weight sets to try in order when --weights is not given.
# These are broadly-trained models that generalise across regions.
DEFAULT_WEIGHTS = ["instance", "stead", "ethz", "scedc", "geofon"]

MODEL_CLASSES = {
    "phasenet": "PhaseNet",
    "eqtransformer": "EQTransformer",
    "eqt": "EQTransformer",
    "gpd": "GPD",
}


def load_model(model_name, weights):
    import seisbench.models as sbm

    cls_name = MODEL_CLASSES.get(model_name.lower())
    if cls_name is None:
        raise SystemExit(
            f"Unknown model '{model_name}'. Choose one of: {sorted(MODEL_CLASSES)}"
        )
    model_cls = getattr(sbm, cls_name)

    candidates = [weights] if weights else DEFAULT_WEIGHTS
    last_err = None
    for w in candidates:
        try:
            model = model_cls.from_pretrained(w)
            model.eval()
            print(f"Loaded {cls_name} pretrained weights '{w}'", file=sys.stderr)
            return model
        except Exception as e:  # noqa: BLE001 - try the next weight set
            last_err = e
            print(f"  could not load weights '{w}': {e}", file=sys.stderr)
    raise SystemExit(
        f"Failed to load any pretrained weights for {cls_name}. "
        f"Last error: {last_err}. SeisBench downloads weights on first use - "
        f"check network access or a pre-populated weights cache."
    )


def to_naive_iso(utcdatetime):
    """ObsPy UTCDateTime -> tz-naive ISO string in UTC."""
    return pd.Timestamp(utcdatetime.datetime).isoformat()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--waveform", required=True, help="Path to MSEED file")
    ap.add_argument("--stations", required=True, help="Path to stations.csv (read for sanity only)")
    ap.add_argument("--out", default="picks.csv")
    ap.add_argument("--model", default="phasenet")
    ap.add_argument("--weights", default=None, help="Single pretrained weight set; default tries several")
    ap.add_argument("--p-threshold", type=float, default=0.2)
    ap.add_argument("--s-threshold", type=float, default=0.2)
    ap.add_argument("--batch-size", type=int, default=256)
    args = ap.parse_args()

    from obspy import read

    stream = read(args.waveform)
    print(f"Read {len(stream)} traces from {args.waveform}", file=sys.stderr)
    # Merge fragmented traces so each channel is continuous for annotation.
    try:
        stream.merge(method=1, fill_value="interpolate")
    except Exception as e:  # noqa: BLE001
        print(f"stream.merge warning ({e}); annotating un-merged stream", file=sys.stderr)

    model = load_model(args.model, args.weights)

    # classify() resamples/normalises internally to the model's expected rate.
    classify_kwargs = dict(
        batch_size=args.batch_size,
        P_threshold=args.p_threshold,
        S_threshold=args.s_threshold,
    )
    try:
        outputs = model.classify(stream, **classify_kwargs)
    except TypeError:
        # Some versions/models name thresholds differently; retry minimally.
        print("classify() rejected threshold kwargs; retrying without them", file=sys.stderr)
        outputs = model.classify(stream, batch_size=args.batch_size)

    picks = getattr(outputs, "picks", outputs)

    rows = []
    for p in picks:
        trace_id = str(p.trace_id)
        parts = trace_id.split(".")
        station = ".".join(parts[:2]) if len(parts) >= 2 else trace_id
        peak = getattr(p, "peak_value", None)
        rows.append(
            {
                "trace_id": trace_id,
                "station": station,
                "phase": str(p.phase).upper(),
                "time": to_naive_iso(p.peak_time),
                "probability": float(peak) if peak is not None else 1.0,
            }
        )

    df = pd.DataFrame(rows, columns=["trace_id", "station", "phase", "time", "probability"])
    df = df.sort_values("time").reset_index(drop=True)
    df.to_csv(args.out, index=False)

    if df.empty:
        print(
            "WARNING: no picks produced. Lower --p-threshold/--s-threshold or "
            "try other --weights.",
            file=sys.stderr,
        )
    else:
        n_p = int((df.phase == "P").sum())
        n_s = int((df.phase == "S").sum())
        print(f"Wrote {len(df)} picks ({n_p} P, {n_s} S) to {args.out}")


if __name__ == "__main__":
    main()
