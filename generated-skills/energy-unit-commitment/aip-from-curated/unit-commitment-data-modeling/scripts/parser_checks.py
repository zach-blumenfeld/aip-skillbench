"""Parser-level validation for normalized unit-commitment input data.

Run these checks AFTER mapping source data into the normalized `case`
representation described in `references/parsing-patterns.md` and BEFORE
building any optimization model. The checks catch the classes of
schema-vs-prose mismatch that quietly produce an infeasible or wrong
model later:

* missing required fields
* duplicate resource IDs
* time-series length mismatches against the horizon `T`
* non-finite numeric values
* inverted limits (`pmin > pmax`, `min > max`)
* under-specified cost curves and startup tier tables
* non-monotone startup-tier lag thresholds
* inconsistent thermal initial state (`initial_on` vs `initial_on_duration`
  / `initial_off_duration`)

The checker returns a structured report instead of asserting so the
caller can present every problem at once. Treat `ok=False` as a hard
stop: do not solve until every error in `errors` is resolved. `warnings`
are advisory (e.g. repeated cost-curve points).

Input shape — keys may be omitted when not present in the source data;
each block of checks runs only when its inputs are supplied:

    {
      "T": int,
      "thermal_names":   [str, ...],          # optional, for duplicate check
      "renewable_names": [str, ...],          # optional, for duplicate check
      "demand":              [float, ...],    # length T
      "reserve_requirement": [float, ...],    # length T

      "thermal": {                            # per-unit, keyed by name
        "<g>": {
          "pmin": float, "pmax": float,
          "initial_on": 0|1,
          "initial_on_duration": int,         # >=0
          "initial_off_duration": int,        # >=0
          "production_curve": [{"mw": f, "cost": f}, ...],   # >=2 points
          "startup_tiers":    [{"lag": int, "cost": f}, ...] # >=1 tier
        }, ...
      },

      "renewable": {                          # per-unit, keyed by name
        "<r>": {
          "min": [float, ...],                # length T
          "max": [float, ...]                 # length T
        }, ...
      }
    }

Output: `{"ok": bool, "errors": [str, ...], "warnings": [str, ...]}`.
"""

from __future__ import annotations

import math
from typing import Any


def _is_finite_number(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _check_length(name: str, seq: Any, T: int, errors: list[str]) -> None:
    if seq is None:
        return
    try:
        n = len(seq)
    except TypeError:
        errors.append(f"{name}: not a sequence")
        return
    if n != T:
        errors.append(f"{name}: length {n} does not match horizon T={T}")


def _check_all_finite(name: str, seq: Any, errors: list[str]) -> None:
    if seq is None:
        return
    for i, v in enumerate(seq):
        if not _is_finite_number(v):
            errors.append(f"{name}[{i}] is not a finite number ({v!r})")
            return


def _check_duplicates(label: str, names: Any, errors: list[str]) -> None:
    if names is None:
        return
    seen: set[str] = set()
    dupes: set[str] = set()
    for n in names:
        if n in seen:
            dupes.add(n)
        seen.add(n)
    if dupes:
        errors.append(f"{label}: duplicate ids {sorted(dupes)}")


def validate_case(case: dict) -> dict:
    """Run all parser-level checks and return a structured report."""
    errors: list[str] = []
    warnings: list[str] = []

    if "T" not in case:
        errors.append("missing required field: T (horizon length)")
        return {"ok": False, "errors": errors, "warnings": warnings}
    try:
        T = int(case["T"])
    except (TypeError, ValueError):
        errors.append(f"T must be an integer, got {case['T']!r}")
        return {"ok": False, "errors": errors, "warnings": warnings}
    if T <= 0:
        errors.append(f"T must be positive, got {T}")
        return {"ok": False, "errors": errors, "warnings": warnings}

    _check_duplicates("thermal_names", case.get("thermal_names"), errors)
    _check_duplicates("renewable_names", case.get("renewable_names"), errors)

    demand = case.get("demand")
    _check_length("demand", demand, T, errors)
    _check_all_finite("demand", demand, errors)

    reserve_req = case.get("reserve_requirement")
    _check_length("reserve_requirement", reserve_req, T, errors)
    _check_all_finite("reserve_requirement", reserve_req, errors)

    thermal = case.get("thermal") or {}
    if not isinstance(thermal, dict):
        errors.append("thermal: expected mapping of name->parameters")
        thermal = {}

    for g, params in thermal.items():
        if not isinstance(params, dict):
            errors.append(f"thermal[{g}]: expected mapping of parameters")
            continue

        pmin = params.get("pmin")
        pmax = params.get("pmax")
        if pmin is None or pmax is None:
            errors.append(f"thermal[{g}]: missing pmin or pmax")
        elif not (_is_finite_number(pmin) and _is_finite_number(pmax)):
            errors.append(f"thermal[{g}]: pmin/pmax not finite numbers")
        elif float(pmin) < 0 or float(pmax) < 0:
            errors.append(f"thermal[{g}]: negative pmin or pmax")
        elif float(pmin) > float(pmax):
            errors.append(
                f"thermal[{g}]: pmin {pmin} exceeds pmax {pmax}"
            )

        initial_on = params.get("initial_on")
        if initial_on not in (None, 0, 1):
            errors.append(
                f"thermal[{g}]: initial_on must be 0 or 1, got {initial_on!r}"
            )
        init_on_dur = params.get("initial_on_duration")
        init_off_dur = params.get("initial_off_duration")
        for label, val in (
            ("initial_on_duration", init_on_dur),
            ("initial_off_duration", init_off_dur),
        ):
            if val is None:
                continue
            try:
                iv = int(val)
            except (TypeError, ValueError):
                errors.append(f"thermal[{g}].{label}: not an integer ({val!r})")
                continue
            if iv < 0:
                errors.append(f"thermal[{g}].{label}: negative ({iv})")

        if initial_on == 1 and isinstance(init_off_dur, int) and init_off_dur > 0:
            errors.append(
                f"thermal[{g}]: initial_on=1 but initial_off_duration>0"
            )
        if initial_on == 0 and isinstance(init_on_dur, int) and init_on_dur > 0:
            errors.append(
                f"thermal[{g}]: initial_on=0 but initial_on_duration>0"
            )

        curve = params.get("production_curve")
        if curve is None:
            errors.append(f"thermal[{g}]: missing production_curve")
        else:
            try:
                n = len(curve)
            except TypeError:
                errors.append(f"thermal[{g}].production_curve: not a sequence")
                n = 0
            if n < 2:
                errors.append(
                    f"thermal[{g}].production_curve: need at least 2 points, got {n}"
                )
            mws_seen: list[float] = []
            for j, pt in enumerate(curve or []):
                if not isinstance(pt, dict) or "mw" not in pt or "cost" not in pt:
                    errors.append(
                        f"thermal[{g}].production_curve[{j}]: missing mw or cost"
                    )
                    continue
                if not (_is_finite_number(pt["mw"]) and _is_finite_number(pt["cost"])):
                    errors.append(
                        f"thermal[{g}].production_curve[{j}]: non-finite mw or cost"
                    )
                    continue
                mw = float(pt["mw"])
                if mw in mws_seen:
                    warnings.append(
                        f"thermal[{g}].production_curve: repeated mw={mw}"
                    )
                mws_seen.append(mw)

        tiers = params.get("startup_tiers")
        if tiers is None:
            errors.append(f"thermal[{g}]: missing startup_tiers")
        else:
            try:
                n = len(tiers)
            except TypeError:
                errors.append(f"thermal[{g}].startup_tiers: not a sequence")
                n = 0
            if n < 1:
                errors.append(
                    f"thermal[{g}].startup_tiers: need at least 1 tier, got {n}"
                )
            lags_seen: list[int] = []
            for j, tier in enumerate(tiers or []):
                if not isinstance(tier, dict) or "lag" not in tier or "cost" not in tier:
                    errors.append(
                        f"thermal[{g}].startup_tiers[{j}]: missing lag or cost"
                    )
                    continue
                try:
                    lag = int(tier["lag"])
                except (TypeError, ValueError):
                    errors.append(
                        f"thermal[{g}].startup_tiers[{j}]: lag not an integer ({tier['lag']!r})"
                    )
                    continue
                if lag < 0:
                    errors.append(
                        f"thermal[{g}].startup_tiers[{j}]: negative lag ({lag})"
                    )
                if not _is_finite_number(tier["cost"]):
                    errors.append(
                        f"thermal[{g}].startup_tiers[{j}]: non-finite cost"
                    )
                if lag in lags_seen:
                    warnings.append(
                        f"thermal[{g}].startup_tiers: repeated lag={lag}"
                    )
                lags_seen.append(lag)
            if lags_seen != sorted(lags_seen):
                warnings.append(
                    f"thermal[{g}].startup_tiers: lags are not in monotone order in source — "
                    "sort by lag before applying the tier rule"
                )

    renewable = case.get("renewable") or {}
    if not isinstance(renewable, dict):
        errors.append("renewable: expected mapping of name->{min, max}")
        renewable = {}

    for r, params in renewable.items():
        if not isinstance(params, dict):
            errors.append(f"renewable[{r}]: expected mapping with min and max")
            continue
        rmin = params.get("min")
        rmax = params.get("max")
        if rmin is None or rmax is None:
            errors.append(f"renewable[{r}]: missing min or max")
            continue
        _check_length(f"renewable[{r}].min", rmin, T, errors)
        _check_length(f"renewable[{r}].max", rmax, T, errors)
        _check_all_finite(f"renewable[{r}].min", rmin, errors)
        _check_all_finite(f"renewable[{r}].max", rmax, errors)
        try:
            for t in range(min(len(rmin), len(rmax))):
                if float(rmin[t]) > float(rmax[t]):
                    errors.append(
                        f"renewable[{r}]: min[{t}]={rmin[t]} > max[{t}]={rmax[t]}"
                    )
                    break
        except (TypeError, ValueError):
            pass

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: parser_checks.py <case.json>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1]) as f:
        case = json.load(f)
    report = validate_case(case)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
