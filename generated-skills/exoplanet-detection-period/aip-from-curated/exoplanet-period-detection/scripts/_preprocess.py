"""Shared preprocessing used by every search script.

Order (matters):
  1. finite mask
  2. sigma clip pass (default sigma=5, around the median)
  3. Savitzky-Golay flatten with a window that is longer than the
     maximum expected transit duration but shorter than any trend
     the search wants to recover
  4. a second gentler sigma clip (default sigma=3) on the detrended flux

Transit-safe defaults: a window of 101 cadences at 30-min cadence
(~2.1 d) preserves transit shapes shorter than a few hours while
removing stellar rotation.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter


def _upper_sigma_clip(flux: np.ndarray, sigma: float) -> np.ndarray:
    """Keep points that are not more than `sigma` MAD above the median.

    One-sided on purpose: transit dips are the signal we want to preserve.
    """
    med = np.median(flux)
    mad = np.median(np.abs(flux - med))
    scale = 1.4826 * mad if mad > 0 else np.std(flux)
    if scale <= 0 or not np.isfinite(scale):
        return np.ones_like(flux, dtype=bool)
    return (flux - med) < sigma * scale


def preprocess(time, flux, flux_err, *, window_length=101, sigma1=5.0, sigma2=5.0):
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    flux_err = np.asarray(flux_err, dtype=float)

    # 1. finite mask
    m = np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
    time, flux, flux_err = time[m], flux[m], flux_err[m]

    # 2. first-pass clip: upper-only so flares/cosmic rays go but transits stay
    m = _upper_sigma_clip(flux, sigma1)
    time, flux, flux_err = time[m], flux[m], flux_err[m]

    # 3. flatten with Savitzky-Golay; window must be odd and <= len(flux)
    n = flux.size
    wl = min(window_length, n - (1 if n % 2 == 0 else 0))
    if wl < 11:
        wl = min(11, n if n % 2 else n - 1)
    if wl % 2 == 0:
        wl -= 1
    if wl >= 5:
        trend = savgol_filter(flux, window_length=wl, polyorder=2, mode="interp")
        trend = np.where(trend <= 0, np.median(flux), trend)
        flat_flux = flux / trend
        flat_err = flux_err / trend
    else:
        flat_flux = flux / np.median(flux)
        flat_err = flux_err / np.median(flux)

    # 4. second-pass clip on the detrended flux, again upper-only so transit
    # dips in `flat_flux` survive.
    m = _upper_sigma_clip(flat_flux, sigma2)
    time, flat_flux, flat_err = time[m], flat_flux[m], flat_err[m]

    return time, flat_flux, flat_err
