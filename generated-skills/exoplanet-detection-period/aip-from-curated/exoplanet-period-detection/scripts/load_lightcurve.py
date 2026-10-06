#!/usr/bin/env python3
"""Load a light curve file into time / flux / flux_err arrays.

Reads one JSON object from stdin, writes one JSON object to stdout.

Supported inputs:
  - CSV / TSV / whitespace-delimited text (header optional) with
    columns in any of these name sets (case-insensitive):
        time, flux, flux_err [, quality]
        time, flux, error    [, quality]
        bjd,  flux, flux_err [, flag]
    When there is no header the columns are assumed to be
    (time, flux, flux_err) and an optional 4th quality column.
  - FITS (via astropy.io.fits) with columns TIME, PDCSAP_FLUX /
    SAP_FLUX, PDCSAP_FLUX_ERR / SAP_FLUX_ERR, QUALITY.

Quality filtering follows the TESS/Kepler convention (0 = good)
by default; set `quality_good_is_zero=false` in the input to flip it.

The flux series is median-normalised so downstream search steps all
operate in relative-flux units.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import numpy as np


def _read_text_table(path: str) -> np.ndarray:
    with open(path, "r") as fh:
        first = fh.readline()
    # Detect delimiter
    if "," in first:
        delim = ","
    elif "\t" in first:
        delim = "\t"
    else:
        delim = None  # whitespace
    # Detect header: any alpha char in first line means header
    has_header = any(c.isalpha() for c in first.replace("e", "").replace("E", ""))
    skip = 1 if has_header else 0
    return np.genfromtxt(path, delimiter=delim, skip_header=skip, dtype=float), (
        first.strip().split(delim) if has_header else None
    )


def _column_index(headers, candidates):
    if headers is None:
        return None
    low = [h.strip().lower() for h in headers]
    for c in candidates:
        if c in low:
            return low.index(c)
    return None


def _load_text(path: str) -> dict:
    data, headers = _read_text_table(path)
    if data.ndim == 1:
        data = data.reshape(-1, data.shape[0])
    if headers:
        t_idx = _column_index(headers, ["time", "bjd", "btjd", "t"])
        f_idx = _column_index(headers, ["flux", "pdcsap_flux", "sap_flux"])
        e_idx = _column_index(
            headers,
            ["flux_err", "error", "err", "pdcsap_flux_err", "sap_flux_err"],
        )
        q_idx = _column_index(headers, ["quality", "flag", "quality_flag"])
    else:
        t_idx, f_idx, e_idx = 0, 1, 2
        q_idx = 3 if data.shape[1] >= 4 else None
    if t_idx is None or f_idx is None:
        raise ValueError("Could not locate time/flux columns")
    time = data[:, t_idx].astype(float)
    flux = data[:, f_idx].astype(float)
    if e_idx is not None and e_idx < data.shape[1]:
        flux_err = data[:, e_idx].astype(float)
    else:
        flux_err = None
    quality = data[:, q_idx].astype(float) if q_idx is not None else None
    return {"time": time, "flux": flux, "flux_err": flux_err, "quality": quality}


def _load_fits(path: str) -> dict:
    from astropy.io import fits

    with fits.open(path) as hdul:
        tbl = hdul[1].data
        names = {n.upper(): n for n in tbl.names}
        tcol = names.get("TIME")
        fcol = (
            names.get("PDCSAP_FLUX") or names.get("SAP_FLUX") or names.get("FLUX")
        )
        ecol = (
            names.get("PDCSAP_FLUX_ERR")
            or names.get("SAP_FLUX_ERR")
            or names.get("FLUX_ERR")
        )
        qcol = names.get("QUALITY")
        time = np.asarray(tbl[tcol], dtype=float)
        flux = np.asarray(tbl[fcol], dtype=float)
        flux_err = np.asarray(tbl[ecol], dtype=float) if ecol else None
        quality = np.asarray(tbl[qcol], dtype=float) if qcol else None
    return {"time": time, "flux": flux, "flux_err": flux_err, "quality": quality}


def _finite_mask(*arrs):
    m = np.ones(arrs[0].shape, dtype=bool)
    for a in arrs:
        if a is None:
            continue
        m &= np.isfinite(a)
    return m


def main() -> int:
    payload = json.load(sys.stdin)
    state: dict[str, Any] = payload.get("currentState", {})
    path = state["lightcurve_path"]
    period_min = float(state.get("period_min", 0.5))
    period_max = float(state.get("period_max", 15.0))
    good_is_zero = bool(state.get("quality_good_is_zero", True))

    if not os.path.exists(path):
        raise FileNotFoundError(f"lightcurve_path does not exist: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext in (".fits", ".fit"):
        data = _load_fits(path)
    else:
        data = _load_text(path)

    time = data["time"]
    flux = data["flux"]
    flux_err = data["flux_err"]
    quality = data["quality"]

    # Finite filter
    m = _finite_mask(time, flux, flux_err)
    time, flux = time[m], flux[m]
    if flux_err is not None:
        flux_err = flux_err[m]
    if quality is not None:
        quality = quality[m]

    # Quality mask
    had_quality = quality is not None
    if had_quality:
        qmask = (quality == 0) if good_is_zero else (quality != 0)
        time, flux = time[qmask], flux[qmask]
        if flux_err is not None:
            flux_err = flux_err[qmask]
        quality = quality[qmask]

    # Normalise flux by median so downstream depth/power compare across sources.
    med = float(np.nanmedian(flux))
    if med <= 0 or not np.isfinite(med):
        raise ValueError("Non-positive or non-finite median flux; cannot normalise")
    flux = flux / med
    if flux_err is not None:
        flux_err = flux_err / med
    else:
        # Estimate per-point uncertainty from residual MAD.
        mad = float(np.nanmedian(np.abs(flux - np.nanmedian(flux))))
        sigma = 1.4826 * mad if mad > 0 else float(np.nanstd(flux))
        if sigma == 0 or not np.isfinite(sigma):
            sigma = 1e-4
        flux_err = np.full_like(flux, sigma)

    n_points = int(time.size)
    if n_points < 50:
        raise ValueError(f"Too few points after filtering: {n_points}")
    span = float(time.max() - time.min())

    # Clamp period_max to half the baseline so TLS can at least see 2 cycles.
    period_max = min(period_max, span / 2.0)
    if period_min >= period_max:
        period_min = max(0.1, min(period_min, period_max * 0.5))

    out = {
        "lightcurve": {
            "time": time.tolist(),
            "flux": flux.tolist(),
            "flux_err": flux_err.tolist(),
        },
        "lightcurve_meta": {
            "n_points": n_points,
            "time_span_days": span,
            "median_flux": med,
            "had_quality_column": had_quality,
        },
        "period_min": period_min,
        "period_max": period_max,
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
