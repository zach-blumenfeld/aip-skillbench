#!/usr/bin/env python3
"""Validate simulation_results.csv, compute ACC performance metrics, and
optionally write acc_report.md.

Requires: Python >= 3.8, pandas, pyyaml.

Usage:
    python3 evaluate.py --results simulation_results.csv --config vehicle_params.yaml \
        [--sensor sensor_data.csv] [--gains tuning_results.yaml] \
        [--tuning-log tuning_log.json] [--report acc_report.md] [--json metrics.json]

Exit 0 when the file is valid and every target passes, 1 when a target
fails, 2 when the results file is malformed. Prints one JSON object.

Metric definitions (also used by tune_pid.py):
  speed_rise_time    10%->90% of set_speed, first cruise segment (the step from rest)
  speed_overshoot    % above set_speed, max ego_speed over ALL cruise rows
  speed_ss_error     max over cruise segments >= 5 s of |set_speed - mean(final 10%)|
  distance_ss_error  mean |distance_error| over steady follow rows: follow mode,
                     >= 5 s after the follow segment began, ego_speed below
                     set_speed - 0.5, and acceleration_cmd not pinned at a limit.
                     Excluded rows are where the gap is not controllable (lead
                     outruns the set speed, or the actuator is saturated while
                     the lead pulls away); they are counted and reported apart
  min_distance       min of the distance column (all rows with a lead)
"""

import argparse
import json
import math
import sys

import pandas as pd
import yaml

COLUMNS = ['time', 'ego_speed', 'acceleration_cmd', 'mode', 'distance_error', 'distance', 'ttc']
MODES = {'cruise', 'follow', 'emergency'}
DEFAULT_TARGETS = {
    'speed_rise_time': 10.0,      # s, strictly less
    'speed_overshoot': 5.0,       # %, strictly less
    'speed_ss_error': 0.5,        # m/s, strictly less
    'distance_ss_error': 2.0,     # m, strictly less
    'min_distance': 5.0,          # m, strictly greater
}
SETTLE_AFTER = 5.0   # s ignored after entering follow
CAP_MARGIN = 0.5     # m/s below set_speed at which the cruise cap counts as active


# --- source metric functions (simulation-metrics skill) -------------------
def rise_time(times, values, target):
    """Calculate rise time (10% to 90% of target)."""
    t10 = t90 = None
    for t, v in zip(times, values):
        if t10 is None and v >= 0.1 * target:
            t10 = t
        if t90 is None and v >= 0.9 * target:
            t90 = t
            break
    if t10 is not None and t90 is not None:
        return t90 - t10
    return None


def overshoot_percent(values, target):
    """Calculate overshoot percentage."""
    max_val = max(values)
    if max_val <= target:
        return 0.0
    return ((max_val - target) / target) * 100


def steady_state_error(values, target, final_fraction=0.1):
    """Calculate steady-state error using final portion of data."""
    n = len(values)
    start = int(n * (1 - final_fraction))
    tail = values[start:] or values[-1:]
    final_avg = sum(tail) / len(tail)
    return abs(target - final_avg)


def settling_time(times, values, target, tolerance=0.02):
    """Time to settle within tolerance of target."""
    band = target * tolerance
    lower, upper = target - band, target + band
    settled_at = None
    for t, v in zip(times, values):
        if v < lower or v > upper:
            settled_at = None
        elif settled_at is None:
            settled_at = t
    return settled_at


# --- helpers ---------------------------------------------------------------
def segments(df, mode):
    """List of DataFrames, one per contiguous run of `mode`."""
    run_id = (df['mode'] != df['mode'].shift()).cumsum()
    return [g for _, g in df[df['mode'] == mode].groupby(run_id[df['mode'] == mode])]


def compute_metrics(df, set_speed, targets=None, accel_limits=(-8.0, 3.0)):
    targets = targets or DEFAULT_TARGETS
    amin, amax = accel_limits
    m = {}
    cruise_segs = segments(df, 'cruise')
    follow_segs = segments(df, 'follow')
    first = cruise_segs[0] if cruise_segs else df
    t, v = first['time'].tolist(), first['ego_speed'].tolist()
    m['speed_rise_time'] = rise_time(t, v, set_speed)
    m['speed_settling_time_2pct'] = settling_time(t, v, set_speed)
    m['speed_overshoot_first_segment'] = overshoot_percent(v, set_speed)
    cruise = df[df['mode'] == 'cruise']
    m['speed_overshoot'] = overshoot_percent(cruise['ego_speed'].tolist(), set_speed) if len(cruise) else 0.0
    m['max_ego_speed'] = float(df['ego_speed'].max())
    seg_err = []
    for s in cruise_segs:
        if s['time'].iloc[-1] - s['time'].iloc[0] >= 5.0:
            seg_err.append({'start': float(s['time'].iloc[0]), 'end': float(s['time'].iloc[-1]),
                            'ss_error': steady_state_error(s['ego_speed'].tolist(), set_speed)})
    m['speed_ss_error_by_segment'] = seg_err
    m['speed_ss_error'] = max((e['ss_error'] for e in seg_err), default=None)

    steady, capped = [], []
    for s in follow_segs:
        s = s[s['time'] >= s['time'].iloc[0] + SETTLE_AFTER]
        sat = (s['acceleration_cmd'] >= amax - 1e-6) | (s['acceleration_cmd'] <= amin + 1e-6)
        ok = (s['ego_speed'] < set_speed - CAP_MARGIN) & ~sat
        steady.append(s[ok])
        capped.append(s[~ok])
    steady = pd.concat(steady) if steady else df.iloc[0:0]
    capped = pd.concat(capped) if capped else df.iloc[0:0]
    follow = df[df['mode'] == 'follow']
    m['distance_ss_error'] = float(steady['distance_error'].abs().mean()) if len(steady) else None
    m['distance_ss_error_rows'] = int(len(steady))
    m['distance_error_follow_all_mean_abs'] = float(follow['distance_error'].abs().mean()) if len(follow) else None
    m['distance_error_follow_median_abs'] = float(follow['distance_error'].abs().median()) if len(follow) else None
    m['distance_error_capped_rows'] = int(len(capped))
    m['distance_error_capped_mean'] = float(capped['distance_error'].mean()) if len(capped) else None
    lead = df[df['distance'].notna()]
    m['min_distance'] = float(lead['distance'].min()) if len(lead) else None
    m['min_ttc'] = float(df['ttc'].min()) if df['ttc'].notna().any() else None
    m['duration'] = float(df['time'].iloc[-1] - df['time'].iloc[0])
    m['mode_counts'] = {k: int(c) for k, c in df['mode'].value_counts().items()}
    m['emergency_events'] = len(segments(df, 'emergency'))
    m['accel_min'] = float(df['acceleration_cmd'].min())
    m['accel_max'] = float(df['acceleration_cmd'].max())

    checks = {
        'speed_rise_time': m['speed_rise_time'] is not None and m['speed_rise_time'] < targets['speed_rise_time'],
        'speed_overshoot': m['speed_overshoot'] < targets['speed_overshoot'],
        'speed_ss_error': m['speed_ss_error'] is not None and m['speed_ss_error'] < targets['speed_ss_error'],
        'distance_ss_error': m['distance_ss_error'] is None or m['distance_ss_error'] < targets['distance_ss_error'],
        'min_distance': m['min_distance'] is None or m['min_distance'] > targets['min_distance'],
    }
    return m, checks


def validate(df, config, sensor=None):
    """Return a list of format problems (empty when valid)."""
    errs = []
    if df.columns.tolist() != COLUMNS:
        errs.append(f"columns {df.columns.tolist()} != {COLUMNS}")
        return errs
    if sensor is not None:
        if len(df) != len(sensor):
            errs.append(f"{len(df)} rows but sensor has {len(sensor)}")
        elif (df['time'].round(3).values != sensor['time'].round(3).values).any():
            errs.append("time column does not match sensor time column")
        else:
            lead_present = sensor['lead_speed'].notna() & sensor['distance'].notna()
            bad = (lead_present != (df['mode'] != 'cruise'))
            if bad.any():
                errs.append(f"cruise/lead mismatch at t={df.loc[bad, 'time'].head(5).tolist()}")
    bad_modes = set(df['mode'].dropna()) - MODES
    if bad_modes or df['mode'].isna().any():
        errs.append(f"invalid modes {bad_modes or 'NaN'}")
    cruise = df[df['mode'] == 'cruise']
    if cruise[['distance_error', 'distance', 'ttc']].notna().any().any():
        errs.append("cruise rows must leave distance_error, distance, ttc empty")
    nc = df[df['mode'] != 'cruise']
    if nc[['distance_error', 'distance']].isna().any().any():
        errs.append("follow/emergency rows need distance_error and distance")
    veh = config.get('vehicle', {})
    amax, amin = float(veh.get('max_acceleration', 3.0)), -abs(float(veh.get('max_deceleration', -8.0)))
    if df['acceleration_cmd'].max() > amax + 1e-6 or df['acceleration_cmd'].min() < amin - 1e-6:
        errs.append(f"acceleration_cmd outside [{amin}, {amax}]")
    if (df['ego_speed'] < -1e-9).any():
        errs.append("negative ego_speed")
    if df[['time', 'ego_speed', 'acceleration_cmd']].isna().any().any():
        errs.append("time/ego_speed/acceleration_cmd must never be empty")
    return errs


def accel_limits(config):
    veh = config.get('vehicle', {})
    return -abs(float(veh.get('max_deceleration', -8.0))), float(veh.get('max_acceleration', 3.0))


def parse_targets(items):
    targets = dict(DEFAULT_TARGETS)
    for item in items or []:
        key, _, val = item.partition('=')
        if key not in targets:
            sys.exit(f"ERROR: unknown target {key!r}; use one of {list(targets)}")
        targets[key] = float(val)
    return targets


def _fmt(x, nd=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 'n/a'
    return f"{x:.{nd}f}"


def write_report(path, config, gains, metrics, checks, targets, tuning_log=None):
    acc, veh = config.get('acc_settings', {}), config.get('vehicle', {})
    dt = (config.get('simulation') or {}).get('dt', 0.1)
    gs, gd = gains.get('pid_speed', {}), gains.get('pid_distance', {})
    status = lambda k: 'PASS' if checks[k] else 'FAIL'  # noqa: E731
    lines = [
        "# Adaptive Cruise Control (ACC) Simulation Report", "",
        "## System Design", "",
        "### Architecture",
        "- `pid_controller.py` - `PIDController(kp, ki, kd)`: discrete PID "
        "(`reset()`, `compute(error, dt)`), integral = sum(error*dt), derivative = (error - prev_error)/dt.",
        "- `acc_system.py` - `AdaptiveCruiseControl(config)`: reads the nested `vehicle_params.yaml` dict, "
        "selects the mode, runs a speed PID and a distance PID, clamps the command, "
        "and returns `(acceleration_cmd, mode, distance_error)`.",
        "- `simulation.py` - loads gains from `tuning_results.yaml` at runtime, drives the lead vehicle "
        "from `sensor_data.csv`, integrates the ego vehicle with a kinematic model "
        f"(v <- max(0, v + a*dt), dt = {dt} s) and writes `simulation_results.csv`.", "",
        "### Operating modes",
        f"- **cruise** (no lead vehicle detected): track the set speed {acc.get('set_speed')} m/s with "
        "the speed PID on `set_speed - ego_speed`.",
        "- **follow** (lead vehicle present, TTC >= threshold): hold the time-headway gap "
        f"`d_safe = ego_speed * {acc.get('time_headway')} s + {acc.get('min_distance')} m`; "
        "command = distance PID on `distance - d_safe` + speed PID on `lead_speed - ego_speed`, "
        "capped so following never accelerates the car above the set speed.",
        f"- **emergency** (TTC = distance / (ego_speed - lead_speed) < {acc.get('emergency_ttc_threshold')} s): "
        f"full braking at {veh.get('max_deceleration')} m/s^2.", "",
        "### Safety features",
        f"- Acceleration command clamped to [{veh.get('max_deceleration')}, {veh.get('max_acceleration')}] m/s^2.",
        "- TTC-triggered emergency braking; TTC is undefined (not approaching) when ego is not faster than the lead.",
        f"- Standstill gap {acc.get('min_distance')} m plus a speed-proportional headway.",
        "- Anti-windup (integration frozen while the command saturates) and PID reset on every mode change.",
        "- Speed never negative; follow mode never exceeds the set speed.", "",
        "## PID Tuning Methodology", "",
    ]
    if tuning_log:
        lines += [
            f"- Automated two-stage grid search over {tuning_log.get('evaluated', 'n/a')} closed-loop "
            "simulations of the full scenario (same code path as `simulation.py`).",
            "- Stage 1 tuned the speed PID (rise time, overshoot, speed steady-state error); "
            "stage 2 tuned the distance PID for the best speed candidates (distance steady-state error, "
            "minimum gap, emergency events); a final local refinement perturbed the best set.",
            "- Candidates violating any target were rejected; the rest were ranked by the sum of "
            "metric/target ratios (lower is better), following the manual rule set: raise Kp for speed, "
            "add Ki for steady-state error, add Kd only if it reduces overshoot.",
            f"- Constraints: kp in (0, 10), ki in [0, 5), kd in [0, 5); passing candidates: "
            f"{tuning_log.get('passing', 'n/a')}.", "",
        ]
    else:
        lines += ["- Gains tuned by closed-loop simulation against the targets below "
                  "(Ki = Kd = 0, raise Kp, add Ki for steady-state error, Kd for overshoot).", ""]
    lines += [
        "### Final gains (`tuning_results.yaml`)", "",
        "| Controller | Kp | Ki | Kd |", "|---|---|---|---|",
        f"| Speed | {gs.get('kp')} | {gs.get('ki')} | {gs.get('kd')} |",
        f"| Distance | {gd.get('kp')} | {gd.get('ki')} | {gd.get('kd')} |", "",
        "## Simulation Results", "",
        f"{metrics['duration']:g} s scenario, {sum(metrics['mode_counts'].values())} steps; mode counts: "
        + ", ".join(f"{k} {v}" for k, v in metrics['mode_counts'].items())
        + f"; emergency events: {metrics['emergency_events']}.", "",
        "### Performance metrics", "",
        "| Metric | Value | Target | Status |", "|---|---|---|---|",
        f"| Speed rise time (10-90%) | {_fmt(metrics['speed_rise_time'], 2)} s | < {targets['speed_rise_time']} s | {status('speed_rise_time')} |",
        f"| Speed overshoot | {_fmt(metrics['speed_overshoot'], 2)} % | < {targets['speed_overshoot']} % | {status('speed_overshoot')} |",
        f"| Speed steady-state error | {_fmt(metrics['speed_ss_error'])} m/s | < {targets['speed_ss_error']} m/s | {status('speed_ss_error')} |",
        f"| Distance steady-state error | {_fmt(metrics['distance_ss_error'])} m | < {targets['distance_ss_error']} m | {status('distance_ss_error')} |",
        f"| Minimum distance | {_fmt(metrics['min_distance'], 2)} m | > {targets['min_distance']} m | {status('min_distance')} |",
        "",
        f"- Settling time (2% band): {_fmt(metrics['speed_settling_time_2pct'], 1)} s; max ego speed "
        f"{_fmt(metrics['max_ego_speed'], 2)} m/s; minimum TTC {_fmt(metrics['min_ttc'], 2)} s; "
        f"acceleration range [{_fmt(metrics['accel_min'], 2)}, {_fmt(metrics['accel_max'], 2)}] m/s^2.",
        f"- Distance steady-state error is the mean |distance_error| over {metrics['distance_ss_error_rows']} "
        f"steady follow rows (>= {SETTLE_AFTER:g} s after entering follow, set-speed cap inactive, "
        "acceleration not saturated). "
        f"In {metrics['distance_error_capped_rows']} other follow rows the gap was not controllable - the lead "
        "drove faster than the set speed (ego holds the set speed) or pulled away while ego was already at "
        f"full acceleration - so the gap grew (mean distance_error {_fmt(metrics['distance_error_capped_mean'], 1)} m); "
        f"over all follow rows the median |distance_error| is {_fmt(metrics['distance_error_follow_median_abs'], 2)} m.",
        f"- Overall: {'all targets met' if all(checks.values()) else 'targets missed: ' + ', '.join(k for k, ok in checks.items() if not ok)}.",
        "",
    ]
    with open(path, 'w') as f:
        f.write("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate ACC results and compute metrics")
    ap.add_argument('--results', default='simulation_results.csv')
    ap.add_argument('--config', default='vehicle_params.yaml')
    ap.add_argument('--sensor', default=None, help='sensor_data.csv, to check row count/time/lead alignment')
    ap.add_argument('--gains', default='tuning_results.yaml')
    ap.add_argument('--tuning-log', default=None)
    ap.add_argument('--report', default=None, help='write acc_report.md here')
    ap.add_argument('--json', default=None, help='also write the metrics JSON here')
    ap.add_argument('--target', action='append', default=[], metavar='KEY=VALUE',
                    help='override a target, e.g. speed_rise_time=8 (keys: %s)' % ', '.join(DEFAULT_TARGETS))
    args = ap.parse_args(argv)

    with open(args.config) as f:
        config = yaml.safe_load(f) or {}
    df = pd.read_csv(args.results)
    sensor = pd.read_csv(args.sensor) if args.sensor else None
    errs = validate(df, config, sensor)
    if errs:
        print(json.dumps({'valid': False, 'errors': errs}, indent=2))
        return 2
    targets = parse_targets(args.target)
    set_speed = float(config.get('acc_settings', {}).get('set_speed', 30.0))
    metrics, checks = compute_metrics(df, set_speed, targets, accel_limits(config))
    out = {'valid': True, 'all_pass': all(checks.values()), 'checks': checks, 'metrics': metrics}
    print(json.dumps(out, indent=2))
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(out, f, indent=2)
    if args.report:
        with open(args.gains) as f:
            gains = yaml.safe_load(f) or {}
        log = None
        if args.tuning_log:
            with open(args.tuning_log) as f:
                log = json.load(f)
        write_report(args.report, config, gains, metrics, checks, targets, log)
        print(f"wrote {args.report}", file=sys.stderr)
    return 0 if out['all_pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
