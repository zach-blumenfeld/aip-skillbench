#!/usr/bin/env python3
"""Tune speed and distance PID gains by closed-loop grid search; write
tuning_results.yaml.

Requires: Python >= 3.8, pandas, pyyaml. Imports run_simulation from the
workdir's simulation.py (so tuning uses the exact code the deliverable runs)
and the metric functions from evaluate.py next to this script.

Usage:
    python3 tune_pid.py --workdir /root [--config vehicle_params.yaml]
        [--sensor sensor_data.csv] [--output tuning_results.yaml]
        [--log tuning_log.json] [--target KEY=VALUE ...]

Method (manual rules, automated): stage 1 grids the speed PID (Ki/Kd from 0
upward) with mid distance gains; stage 2 grids the distance PID for the 5
best speed sets; stage 3 perturbs the best set +-25% per gain. Candidates
that miss any target are rejected; the rest are ranked by sum(metric/target)
plus a small penalty per emergency event. Bounds: kp in (0,10), ki in [0,5),
kd in [0,5). Exit 0 if a passing set was written, 1 if only the best failing
set could be written.
"""

import argparse
import json
import os
import sys
import time

import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from evaluate import accel_limits, compute_metrics, parse_targets  # noqa: E402

SPEED_GRID = {'kp': [0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0],
              'ki': [0.0, 0.01, 0.03, 0.05, 0.1, 0.2],
              'kd': [0.0, 0.05, 0.1]}
DIST_GRID = {'kp': [0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0],
             'ki': [0.0, 0.01, 0.02, 0.05, 0.1],
             'kd': [0.0, 0.05, 0.1, 0.3]}
DIST_START = {'kp': 0.3, 'ki': 0.01, 'kd': 0.0}
BOUNDS = {'kp': (1e-3, 9.99), 'ki': (0.0, 4.99), 'kd': (0.0, 4.99)}


def score(metrics, checks, targets):
    if not all(checks.values()):
        return float('inf'), sum(not v for v in checks.values())
    s = metrics['speed_rise_time'] / targets['speed_rise_time']
    s += metrics['speed_overshoot'] / targets['speed_overshoot']
    s += metrics['speed_ss_error'] / targets['speed_ss_error']
    if metrics['distance_ss_error'] is not None:
        s += metrics['distance_ss_error'] / targets['distance_ss_error']
    if metrics['min_distance'] is not None:
        s += targets['min_distance'] / metrics['min_distance']
    s += 0.05 * metrics['emergency_events']
    return s, 0


def failing_rank(metrics, checks, targets):
    """Order for failing candidates: fewest failed checks, then normalised miss."""
    miss = 0.0
    for k, ok in checks.items():
        if ok:
            continue
        v = metrics.get(k)
        if v is None:
            miss += 10
        elif k == 'min_distance':
            miss += targets[k] / max(v, 1e-6)
        else:
            miss += v / targets[k]
    return sum(not v for v in checks.values()), miss


def main(argv=None):
    ap = argparse.ArgumentParser(description="Grid-search ACC PID gains")
    ap.add_argument('--workdir', default='.', help='folder holding simulation.py, acc_system.py, pid_controller.py')
    ap.add_argument('--config', default='vehicle_params.yaml')
    ap.add_argument('--sensor', default='sensor_data.csv')
    ap.add_argument('--output', default='tuning_results.yaml')
    ap.add_argument('--log', default=None, help='write a JSON tuning log (for the report)')
    ap.add_argument('--target', action='append', default=[], metavar='KEY=VALUE')
    args = ap.parse_args(argv)

    workdir = os.path.abspath(args.workdir)
    rel = lambda p: p if os.path.isabs(p) else os.path.join(workdir, p)  # noqa: E731
    sys.path.insert(0, workdir)
    try:
        from simulation import run_simulation
    except ImportError as e:
        sys.exit(f"ERROR: cannot import run_simulation from {workdir}/simulation.py: {e}")

    with open(rel(args.config)) as f:
        config = yaml.safe_load(f) or {}
    sensor = pd.read_csv(rel(args.sensor), na_values=['', 'NA', 'null', 'None', 'nan'])
    targets = parse_targets(args.target)
    set_speed = float(config.get('acc_settings', {}).get('set_speed', 30.0))

    cache = {}
    t0 = time.time()

    def evaluate(sp, dp):
        key = (tuple(sp[k] for k in 'kp ki kd'.split()), tuple(dp[k] for k in 'kp ki kd'.split()))
        if key not in cache:
            df = run_simulation(config, sensor, {'pid_speed': sp, 'pid_distance': dp})
            m, c = compute_metrics(df, set_speed, targets, accel_limits(config))
            cache[key] = (score(m, c, targets), m, c, sp, dp)
        return cache[key]

    def grid(g):
        return [{'kp': p, 'ki': i, 'kd': d} for p in g['kp'] for i in g['ki'] for d in g['kd']]

    # Stage 1: speed loop. Rank on speed metrics only (distance gains held).
    stage1 = []
    for sp in grid(SPEED_GRID):
        (_, _), m, c, _, _ = evaluate(sp, DIST_START)
        speed_ok = c['speed_rise_time'] and c['speed_overshoot'] and c['speed_ss_error']
        s = (0 if speed_ok else 100) + (m['speed_rise_time'] or 99) / targets['speed_rise_time'] \
            + m['speed_overshoot'] / targets['speed_overshoot'] + (m['speed_ss_error'] or 99) / targets['speed_ss_error']
        stage1.append((s, sp))
    stage1.sort(key=lambda x: x[0])
    top_speed = [sp for _, sp in stage1[:5]]

    # Stage 2: distance loop for the best speed sets.
    for sp in top_speed:
        for dp in grid(DIST_GRID):
            evaluate(sp, dp)

    def best():
        items = list(cache.values())
        passing = [it for it in items if it[0][0] != float('inf')]
        if passing:
            return min(passing, key=lambda it: it[0][0]), True
        return min(items, key=lambda it: failing_rank(it[1], it[2], targets)), False

    # Stage 3: local refinement around the best set.
    (b, ok) = best()
    for _ in range(2):
        _, _, _, bsp, bdp = b
        for which in ('speed', 'distance'):
            for k in ('kp', 'ki', 'kd'):
                for f in (0.75, 1.25):
                    sp, dp = dict(bsp), dict(bdp)
                    tgt = sp if which == 'speed' else dp
                    v = tgt[k] * f if tgt[k] > 0 else (0.01 if f > 1 else 0.0)
                    lo, hi = BOUNDS[k]
                    tgt[k] = round(min(max(v, lo), hi), 4)
                    evaluate(sp, dp)
        b, ok = best()

    (sc, _), m, c, sp, dp = b
    result = {'pid_speed': {k: float(sp[k]) for k in ('kp', 'ki', 'kd')},
              'pid_distance': {k: float(dp[k]) for k in ('kp', 'ki', 'kd')}}
    out = rel(args.output)
    with open(out, 'w') as f:
        yaml.dump(result, f, default_flow_style=False, sort_keys=False)

    passing = sum(1 for it in cache.values() if it[0][0] != float('inf'))
    log = {'evaluated': len(cache), 'passing': passing, 'seconds': round(time.time() - t0, 1),
           'all_pass': ok, 'score': None if sc == float('inf') else sc, 'gains': result,
           'checks': c, 'metrics': {k: v for k, v in m.items() if not isinstance(v, (list, dict))}}
    if args.log:
        with open(rel(args.log), 'w') as f:
            json.dump(log, f, indent=2)
    print(json.dumps(log, indent=2))
    print(f"wrote {out}", file=sys.stderr)
    if not ok:
        print("WARNING: no candidate met every target; best failing set written. "
              "See failing checks above.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
