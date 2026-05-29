"""Independent feasibility checks for a unit-commitment schedule.

This module is the canonical encoding of the operating-rules validation
the skill describes. Call `validate_schedule(schedule, system)` after the
schedule arrays have been extracted into the report convention. The
returned report lists every violation; an empty `errors` list (and `ok=True`)
is the only signal it is safe to write `"pass"` fields.

The validator is convention-aware: pass `production_convention="actual"`
when `production[g, t]` is actual MW output, or `"above_min"` when it is
output above `pmin[g] * u[g, t]`. Reserve, ramping, and capacity checks
are applied consistently with that choice.

Data contract
-------------

`schedule` (dict):
  T          : int — number of periods.
  thermal    : list[dict] — one per thermal unit. Keys:
                 id        : str
                 u         : list[int]      length T, binary commitment
                 start     : list[int]      length T, binary startup transition
                 stop      : list[int]      length T, binary shutdown transition
                 production: list[float]    length T (see production_convention)
                 reserve   : list[float]    length T, scheduled spinning reserve
  renewable  : list[dict] — one per renewable unit. Keys:
                 id        : str
                 output    : list[float]    length T

`system` (dict):
  demand              : list[float] length T
  reserve_requirement : list[float] length T
  thermal             : list[dict] keyed by id with:
                          pmin                       : float
                          pmax                       : float
                          ramp_up                    : float
                          ramp_down                  : float
                          min_up                     : int  (periods)
                          min_down                   : int  (periods)
                          initial_on                 : int  (0/1)
                          initial_above_min          : float (MW above pmin at t=-1)
                          initial_on_duration        : int  (periods already on at t=-1)
                          initial_off_duration       : int  (periods already off at t=-1)
                          startup_limit              : float | None — max total MW
                                                       allowed during the startup
                                                       period (if applicable)
                          must_run                   : list[int] | None — periods
                                                       (indices) where u must be 1
  renewable           : list[dict] keyed by id with:
                          min : list[float] length T
                          max : list[float] length T
  reserve_can_count_renewable : bool — default False; the skill warns against
                                 counting renewable headroom as reserve unless
                                 the prompt explicitly allows it.

Either pass `system['thermal']` / `system['renewable']` as a dict keyed by
id, or as a list of dicts each carrying `id`. The validator normalizes both.

Tolerances
----------

`tol` is the absolute tolerance used for floating-point inequality
comparisons (demand balance, ramping, capacity). Default 1e-6.
"""

from __future__ import annotations

from typing import Any


def _as_id_map(items: Any) -> dict[str, dict]:
    if isinstance(items, dict):
        return items
    return {item["id"]: item for item in items}


def _check_length(name: str, seq: Any, T: int, errors: list[str]) -> bool:
    if not hasattr(seq, "__len__"):
        errors.append(f"{name}: expected sequence of length {T}, got non-sequence")
        return False
    if len(seq) != T:
        errors.append(f"{name}: expected length {T}, got {len(seq)}")
        return False
    return True


def _is_binary(x: Any) -> bool:
    return x in (0, 1, 0.0, 1.0)


def validate_schedule(
    schedule: dict,
    system: dict,
    production_convention: str = "actual",
    tol: float = 1e-6,
) -> dict:
    """Return a structured validation report.

    The report has shape:
        {
          "ok": bool,
          "errors": [str, ...],
          "warnings": [str, ...],
          "totals": {
            "demand_balance_residual_max": float,
            "reserve_shortfall_max": float,
            ...
          }
        }
    """
    if production_convention not in ("actual", "above_min"):
        raise ValueError(
            "production_convention must be 'actual' or 'above_min', "
            f"got {production_convention!r}"
        )

    errors: list[str] = []
    warnings: list[str] = []
    T = schedule["T"]

    thermal_units = schedule["thermal"]
    renewable_units = schedule.get("renewable", [])
    sys_thermal = _as_id_map(system["thermal"])
    sys_renewable = _as_id_map(system.get("renewable", {}))
    demand = system["demand"]
    reserve_req = system["reserve_requirement"]
    reserve_can_count_renewable = system.get("reserve_can_count_renewable", False)

    _check_length("demand", demand, T, errors)
    _check_length("reserve_requirement", reserve_req, T, errors)

    # Resources appear exactly once.
    seen_thermal: set[str] = set()
    for u in thermal_units:
        if u["id"] in seen_thermal:
            errors.append(f"thermal unit {u['id']!r} appears more than once")
        seen_thermal.add(u["id"])
    missing_thermal = set(sys_thermal) - seen_thermal
    extra_thermal = seen_thermal - set(sys_thermal)
    if missing_thermal:
        errors.append(f"missing thermal units in schedule: {sorted(missing_thermal)}")
    if extra_thermal:
        errors.append(f"unknown thermal units in schedule: {sorted(extra_thermal)}")

    seen_renew: set[str] = set()
    for r in renewable_units:
        if r["id"] in seen_renew:
            errors.append(f"renewable unit {r['id']!r} appears more than once")
        seen_renew.add(r["id"])

    demand_residuals: list[float] = []
    reserve_shortfalls: list[float] = []

    for ug in thermal_units:
        gid = ug["id"]
        spec = sys_thermal.get(gid)
        if spec is None:
            continue

        if not (_check_length(f"u[{gid}]", ug["u"], T, errors)
                and _check_length(f"start[{gid}]", ug["start"], T, errors)
                and _check_length(f"stop[{gid}]", ug["stop"], T, errors)
                and _check_length(f"production[{gid}]", ug["production"], T, errors)
                and _check_length(f"reserve[{gid}]", ug["reserve"], T, errors)):
            continue

        pmin = spec["pmin"]
        pmax = spec["pmax"]
        cap = pmax - pmin
        ramp_up = spec["ramp_up"]
        ramp_down = spec["ramp_down"]
        min_up = spec["min_up"]
        min_down = spec["min_down"]
        initial_on = int(spec["initial_on"])
        initial_above_min = float(spec.get("initial_above_min", 0.0))
        initial_on_duration = int(spec.get("initial_on_duration", 0))
        initial_off_duration = int(spec.get("initial_off_duration", 0))
        startup_limit = spec.get("startup_limit")
        must_run = spec.get("must_run") or []

        # Binary checks.
        for t in range(T):
            for field in ("u", "start", "stop"):
                if not _is_binary(ug[field][t]):
                    errors.append(
                        f"{field}[{gid}, {t}] = {ug[field][t]!r} is not binary"
                    )

        # Transition consistency.
        prev_on = initial_on
        for t in range(T):
            u_t = int(ug["u"][t])
            s_t = int(ug["start"][t])
            d_t = int(ug["stop"][t])
            if u_t - prev_on != s_t - d_t:
                errors.append(
                    f"transition mismatch at {gid} t={t}: "
                    f"u={u_t} prev_u={prev_on} start={s_t} stop={d_t}"
                )
            if s_t + d_t > 1:
                errors.append(
                    f"simultaneous start and stop at {gid} t={t}"
                )
            prev_on = u_t

        # Must-run periods (indices into [0, T)).
        for t in must_run:
            if not (0 <= t < T):
                warnings.append(f"must_run period {t} for {gid} outside horizon")
                continue
            if int(ug["u"][t]) != 1:
                errors.append(f"must-run unit {gid} offline at t={t}")

        # Capacity bounds and offline zeros.
        for t in range(T):
            u_t = int(ug["u"][t])
            p = float(ug["production"][t])
            r = float(ug["reserve"][t])

            if r < -tol:
                errors.append(f"reserve[{gid}, {t}] = {r} < 0")
            if u_t == 0:
                if abs(p) > tol:
                    errors.append(
                        f"offline production[{gid}, {t}] = {p} is nonzero"
                    )
                if abs(r) > tol:
                    errors.append(
                        f"offline reserve[{gid}, {t}] = {r} is nonzero"
                    )
                continue

            if production_convention == "actual":
                if p < pmin - tol or p > pmax + tol:
                    errors.append(
                        f"production[{gid}, {t}] = {p} outside [{pmin}, {pmax}]"
                    )
                # Joint headroom: production + reserve <= pmax * u
                if p + r > pmax * u_t + tol:
                    errors.append(
                        f"reserve deliverability at {gid} t={t}: "
                        f"production+reserve = {p + r} > pmax * u = {pmax * u_t}"
                    )
            else:  # above_min
                if p < -tol or p > cap * u_t + tol:
                    errors.append(
                        f"p_above_min[{gid}, {t}] = {p} outside [0, {cap * u_t}]"
                    )
                rhs = cap * u_t
                if startup_limit is not None:
                    startup_reduction = max(pmax - startup_limit, 0.0)
                    rhs = rhs - startup_reduction * int(ug["start"][t])
                if p + r > rhs + tol:
                    errors.append(
                        f"reserve deliverability at {gid} t={t}: "
                        f"p_above_min+reserve = {p + r} > {rhs}"
                    )

            # Actual-MW startup capability check (only applies if convention is actual).
            if (
                production_convention == "actual"
                and startup_limit is not None
                and int(ug["start"][t]) == 1
                and p + r > startup_limit + tol
            ):
                errors.append(
                    f"startup capability at {gid} t={t}: "
                    f"production+reserve = {p + r} > startup_limit = {startup_limit}"
                )

        # Ramping. The skill recommends checking ramp_up against
        # production + reserve so reserve is deliverable on the next period.
        if production_convention == "above_min":
            prev = initial_above_min
        else:
            # Convert actual to above-min for ramp comparisons.
            prev = initial_above_min  # caller supplies as above-min; document this.
        for t in range(T):
            if production_convention == "above_min":
                p_now = float(ug["production"][t])
            else:
                p_now = float(ug["production"][t]) - pmin * int(ug["u"][t])
            r_now = float(ug["reserve"][t])
            up_move = (p_now + r_now) - prev
            down_move = prev - p_now
            if up_move > ramp_up + tol:
                errors.append(
                    f"ramp-up violation at {gid} t={t}: "
                    f"(p+r) - prev = {up_move} > ramp_up = {ramp_up}"
                )
            if down_move > ramp_down + tol:
                errors.append(
                    f"ramp-down violation at {gid} t={t}: "
                    f"prev - p = {down_move} > ramp_down = {ramp_down}"
                )
            prev = p_now

        # Minimum up/down time. Account for pre-horizon time on/off via
        # the initial_on_duration / initial_off_duration fields.
        if initial_on == 1 and initial_on_duration < min_up:
            required = min_up - initial_on_duration
            for t in range(min(required, T)):
                if int(ug["u"][t]) != 1:
                    errors.append(
                        f"min_up not satisfied carrying initial-on at {gid} t={t}"
                    )
        if initial_on == 0 and initial_off_duration < min_down:
            required = min_down - initial_off_duration
            for t in range(min(required, T)):
                if int(ug["u"][t]) != 0:
                    errors.append(
                        f"min_down not satisfied carrying initial-off at {gid} t={t}"
                    )
        for t in range(T):
            if int(ug["start"][t]) == 1:
                for tau in range(t, min(T, t + min_up)):
                    if int(ug["u"][tau]) != 1:
                        errors.append(
                            f"min_up violated at {gid}: start at t={t}, "
                            f"u[{tau}] = {ug['u'][tau]}"
                        )
            if int(ug["stop"][t]) == 1:
                for tau in range(t, min(T, t + min_down)):
                    if int(ug["u"][tau]) != 0:
                        errors.append(
                            f"min_down violated at {gid}: stop at t={t}, "
                            f"u[{tau}] = {ug['u'][tau]}"
                        )

    # Renewable bounds.
    for r in renewable_units:
        rid = r["id"]
        spec = sys_renewable.get(rid)
        if spec is None:
            continue
        if not _check_length(f"renewable_output[{rid}]", r["output"], T, errors):
            continue
        rmin = spec["min"]
        rmax = spec["max"]
        _check_length(f"renewable_min[{rid}]", rmin, T, errors)
        _check_length(f"renewable_max[{rid}]", rmax, T, errors)
        for t in range(T):
            out = float(r["output"][t])
            lo = float(rmin[t])
            hi = float(rmax[t])
            if out < lo - tol or out > hi + tol:
                errors.append(
                    f"renewable_output[{rid}, {t}] = {out} outside [{lo}, {hi}]"
                )

    # System-wide demand balance and reserve requirement.
    for t in range(T):
        thermal_actual = 0.0
        for ug in thermal_units:
            gid = ug["id"]
            spec = sys_thermal.get(gid)
            if spec is None:
                continue
            if production_convention == "actual":
                thermal_actual += float(ug["production"][t])
            else:
                thermal_actual += (
                    float(ug["production"][t]) + spec["pmin"] * int(ug["u"][t])
                )
        renew_total = sum(float(r["output"][t]) for r in renewable_units)
        residual = thermal_actual + renew_total - float(demand[t])
        demand_residuals.append(abs(residual))
        if abs(residual) > tol:
            errors.append(
                f"demand balance violation at t={t}: residual = {residual}"
            )

        reserve_sum = sum(float(ug["reserve"][t]) for ug in thermal_units)
        if reserve_can_count_renewable:
            # The skill warns against this; only allow when system flag set.
            warnings.append(
                f"reserve at t={t} counts renewable headroom — "
                "ensure the prompt explicitly allows this"
            )
        shortfall = float(reserve_req[t]) - reserve_sum
        reserve_shortfalls.append(max(0.0, shortfall))
        if shortfall > tol:
            errors.append(
                f"reserve requirement at t={t}: scheduled = {reserve_sum}, "
                f"required = {reserve_req[t]}, shortfall = {shortfall}"
            )

    totals = {
        "demand_balance_residual_max": max(demand_residuals, default=0.0),
        "reserve_shortfall_max": max(reserve_shortfalls, default=0.0),
        "num_errors": len(errors),
        "num_warnings": len(warnings),
    }

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "totals": totals,
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 3:
        print(
            "usage: feasibility_checks.py <schedule.json> <system.json>",
            file=sys.stderr,
        )
        sys.exit(2)

    with open(sys.argv[1]) as f:
        schedule = json.load(f)
    with open(sys.argv[2]) as f:
        system = json.load(f)
    convention = system.get("production_convention", "actual")
    report = validate_schedule(schedule, system, production_convention=convention)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
