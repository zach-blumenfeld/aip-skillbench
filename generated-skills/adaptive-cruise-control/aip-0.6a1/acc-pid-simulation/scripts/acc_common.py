"""Shared helpers for the acc-pid-simulation skill: metrics, gain search, I/O.

Also usable by hand (the retune step):
  python3 acc_common.py evaluate --output-dir D --config C --sensor S [--targets JSON]
  python3 acc_common.py tune     --output-dir D --config C --sensor S [--targets JSON]
        [--speed-kp 0.5,1,2 --speed-ki 0,0.05 --speed-kd 0 --dist-kp ... --dist-ki ... --dist-kd ...]
"""
import argparse
import importlib
import itertools
import json
import os
import sys

import yaml

DEFAULT_TARGETS = {
    'rise_time_max_s': 10.0,
    'overshoot_max_pct': 5.0,
    'speed_ss_error_max': 0.5,
    'distance_ss_error_max': 2.0,
    'min_distance_min': 5.0,
    'duration_s': 150.0,
}
# Gain search grids. Ranges required by the deliverable: kp in (0,10), ki in [0,5), kd in [0,5).
SPEED_GRID = {'kp': [0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0], 'ki': [0.0, 0.01, 0.05, 0.1, 0.2], 'kd': [0.0, 0.05, 0.1]}
DIST_GRID = {'kp': [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5], 'ki': [0.0, 0.005, 0.01, 0.05], 'kd': [0.0, 0.3, 0.5, 1.0, 1.5, 2.0, 3.0]}
GAIN_BOUNDS = {'kp': (0.0, 10.0), 'ki': (0.0, 5.0), 'kd': (0.0, 5.0)}
SETTLE_WINDOW_S = 5.0   # follow rows within this long of a mode change are transient
SPEED_CAP_TOL = 0.5     # m/s: ego this close to set speed with a too-large gap is speed-limited


def merged_targets(targets):
    out = dict(DEFAULT_TARGETS)
    out.update({k: float(v) for k, v in (targets or {}).items() if v is not None})
    return out


def load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def import_deliverables(output_dir):
    """Import the generated simulation module (and its acc_system/pid_controller) from output_dir."""
    output_dir = os.path.abspath(output_dir)
    if output_dir not in sys.path:
        sys.path.insert(0, output_dir)
    for name in ('pid_controller', 'acc_system', 'simulation'):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    return importlib.import_module('simulation')


# ---- metrics (definitions from the simulation-metrics source skill) ----

def rise_time(times, values, target):
    """10% -> 90% of target."""
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
    max_val = max(values)
    if max_val <= target:
        return 0.0
    return ((max_val - target) / target) * 100


def steady_state_error(values, target, final_fraction=0.1):
    n = len(values)
    start = min(int(n * (1 - final_fraction)), n - 1)
    tail = values[start:]
    return abs(target - sum(tail) / len(tail))


def settling_time(times, values, target, tolerance=0.02):
    band = target * tolerance
    lower, upper = target - band, target + band
    settled_at = None
    for t, v in zip(times, values):
        if v < lower or v > upper:
            settled_at = None
        elif settled_at is None:
            settled_at = t
    return settled_at


def mode_segments(modes):
    segs, start = [], 0
    for i in range(1, len(modes) + 1):
        if i == len(modes) or modes[i] != modes[start]:
            segs.append((modes[start], start, i))
            start = i
    return segs


def compute_metrics(rows, config, targets=None):
    """Performance metrics of one simulation run (rows as written to simulation_results.csv)."""
    targets = merged_targets(targets)
    set_speed = float(config['acc_settings']['set_speed'])
    dt = float(config.get('simulation', {}).get('dt', 0.1))
    times = [r['time'] for r in rows]
    ego = [r['ego_speed'] for r in rows]
    modes = [r['mode'] for r in rows]
    segs = mode_segments(modes)
    cruise_segs = [s for s in segs if s[0] == 'cruise']

    m = {}
    # Speed tracking: the first cruise segment is the step response from the initial speed.
    if cruise_segs:
        _, a, b = cruise_segs[0]
        m['rise_time_s'] = rise_time(times[a:b], ego[a:b], set_speed)
        m['settling_time_2pct_s'] = settling_time(times[a:b], ego[a:b], set_speed)
        m['overshoot_initial_pct'] = overshoot_percent(ego[a:b], set_speed)
    else:
        m['rise_time_s'] = m['settling_time_2pct_s'] = None
        m['overshoot_initial_pct'] = None
    m['overshoot_pct'] = overshoot_percent(ego, set_speed)  # over the whole run, any mode
    long_cruise = [s for s in cruise_segs if (s[2] - s[1]) * dt >= 10.0] or cruise_segs
    per_seg = [{'start_s': times[a], 'end_s': times[b - 1],
                'ss_error': steady_state_error(ego[a:b], set_speed, 0.1)} for _, a, b in long_cruise]
    m['speed_ss_error_by_segment'] = per_seg
    m['speed_ss_error'] = max((p['ss_error'] for p in per_seg), default=None)

    # Distance tracking: steady follow rows only. A row is steady when at least SETTLE_WINDOW_S
    # has passed since the last mode change, set-speed cap (gap too large while ego is at set
    # speed), or actuator saturation (command at an acceleration limit).
    a_max = float(config['vehicle']['max_acceleration'])
    a_min = float(config['vehicle']['max_deceleration'])
    settle_n = int(round(SETTLE_WINDOW_S / dt))
    steady, all_follow = [], []
    last_constrained = -10 ** 9
    for i, r in enumerate(rows):
        de = r['distance_error']
        speed_capped = de is not None and de > 0 and r['ego_speed'] >= set_speed - SPEED_CAP_TOL
        saturated = r['acceleration_cmd'] >= a_max - 1e-9 or r['acceleration_cmd'] <= a_min + 1e-9
        if (i > 0 and modes[i] != modes[i - 1]) or r['mode'] != 'follow' or speed_capped or saturated:
            last_constrained = i
        if r['mode'] != 'follow' or de is None:
            continue
        all_follow.append(abs(de))
        if i - last_constrained >= settle_n:
            steady.append(abs(de))
    m['distance_ss_error'] = sum(steady) / len(steady) if steady else None
    m['distance_ss_error_max'] = max(steady) if steady else None
    m['distance_ss_rows'] = len(steady)
    m['follow_steady_fraction'] = len(steady) / len(all_follow) if all_follow else None
    m['distance_error_mean_abs_all_follow'] = sum(all_follow) / len(all_follow) if all_follow else None

    gaps = [r['distance'] for r in rows if r['distance'] is not None]
    ttcs = [r['ttc'] for r in rows if r['ttc'] is not None]
    m['min_distance'] = min(gaps) if gaps else None
    m['min_ttc_s'] = min(ttcs) if ttcs else None
    m['mode_time_s'] = {k: round(sum(1 for x in modes if x == k) * dt, 3) for k in ('cruise', 'follow', 'emergency')}
    m['emergency_events'] = sum(1 for s in segs if s[0] == 'emergency')
    accels = [r['acceleration_cmd'] for r in rows]
    m['accel_range'] = [min(accels), max(accels)]

    checks = {
        'rise_time': m['rise_time_s'] is not None and m['rise_time_s'] < targets['rise_time_max_s'],
        'overshoot': m['overshoot_pct'] < targets['overshoot_max_pct'],
        'speed_ss_error': m['speed_ss_error'] is not None and m['speed_ss_error'] < targets['speed_ss_error_max'],
        # Following that never settles is a failure, not a pass on no data.
        'distance_ss_error': (not all_follow) or (m['distance_ss_error'] is not None
                                                  and m['distance_ss_error'] < targets['distance_ss_error_max']),
        'min_distance': m['min_distance'] is None or m['min_distance'] > targets['min_distance_min'],
    }
    m['checks'] = checks
    m['targets_met'] = all(checks.values())
    return m


def cost(m, targets, focus):
    """Lower is better. Violations dominate; then normalised metric sizes."""
    t = merged_targets(targets)
    big = 1e3
    parts = []
    if focus in ('speed', 'all'):
        rt = m['rise_time_s'] if m['rise_time_s'] is not None else 10 * t['rise_time_max_s']
        parts += [(rt, t['rise_time_max_s'], 'lt'), (m['overshoot_pct'], t['overshoot_max_pct'], 'lt'),
                  (m['speed_ss_error'] if m['speed_ss_error'] is not None else 1e3, t['speed_ss_error_max'], 'lt')]
    if focus in ('distance', 'all'):
        if m['distance_error_mean_abs_all_follow'] is None:
            dss = 0.0
        elif m['distance_ss_error'] is None:
            dss = 10 * t['distance_ss_error_max']  # never settled
        else:
            dss = m['distance_ss_error']
        md = m['min_distance'] if m['min_distance'] is not None else 1e3
        parts += [(dss, t['distance_ss_error_max'], 'lt'), (m['overshoot_pct'], t['overshoot_max_pct'], 'lt')]
        # min distance: reward margin above the floor
        parts.append((t['min_distance_min'] / max(md, 1e-6) * t['min_distance_min'], t['min_distance_min'], 'lt'))
    c = 0.0
    if focus in ('distance', 'all') and m['follow_steady_fraction'] is not None:
        c += 2.0 * (1.0 - m['follow_steady_fraction'])  # prefer loops that settle, not chatter
    for value, limit, _ in parts:
        ratio = value / limit if limit else value
        c += ratio + (big * (ratio - 1.0) if ratio >= 1.0 else 0.0)
    return c


def grid_search(sim, config, sensor, targets, speed_grid=None, dist_grid=None):
    """Two-stage grid search: speed loop first, then distance loop with the chosen speed gains."""
    speed_grid = speed_grid or SPEED_GRID
    dist_grid = dist_grid or DIST_GRID
    records = sensor.to_dict('records')
    base_dist = {k: float(config.get('pid_distance', {}).get(k, v)) for k, v in (('kp', 0.1), ('ki', 0.01), ('kd', 0.0))}
    log = []

    def evaluate(gains, focus):
        rows = sim.run_simulation(config, records, gains)
        m = compute_metrics(rows, config, targets)
        return cost(m, targets, focus), m

    best = None
    for kp, ki, kd in itertools.product(speed_grid['kp'], speed_grid['ki'], speed_grid['kd']):
        gains = {'pid_speed': {'kp': kp, 'ki': ki, 'kd': kd}, 'pid_distance': base_dist}
        c, m = evaluate(gains, 'speed')
        if best is None or c < best[0] - 1e-9:
            best = (c, gains['pid_speed'], m)
    speed_best = best[1]
    log.append({'stage': 'speed', 'evaluated': len(speed_grid['kp']) * len(speed_grid['ki']) * len(speed_grid['kd']),
                'best': speed_best, 'cost': round(best[0], 4)})

    best = None
    for kp, ki, kd in itertools.product(dist_grid['kp'], dist_grid['ki'], dist_grid['kd']):
        gains = {'pid_speed': speed_best, 'pid_distance': {'kp': kp, 'ki': ki, 'kd': kd}}
        c, m = evaluate(gains, 'all')
        if best is None or c < best[0] - 1e-9:
            best = (c, gains, m)
    log.append({'stage': 'distance', 'evaluated': len(dist_grid['kp']) * len(dist_grid['ki']) * len(dist_grid['kd']),
                'best': best[1]['pid_distance'], 'cost': round(best[0], 4)})
    return best[1], best[2], log


def gains_in_bounds(gains):
    for loop in ('pid_speed', 'pid_distance'):
        for k, (lo, hi) in GAIN_BOUNDS.items():
            v = float(gains[loop][k])
            ok = (lo < v < hi) if k == 'kp' else (lo <= v < hi)
            if not ok:
                return False
    return True


def write_gains(path, gains):
    data = {loop: {k: float(gains[loop][k]) for k in ('kp', 'ki', 'kd')} for loop in ('pid_speed', 'pid_distance')}
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _floats(s):
    return [float(x) for x in s.split(',')] if s else None


def main():
    p = argparse.ArgumentParser(description='Evaluate or re-tune ACC gains against the sensor data.')
    p.add_argument('action', choices=['evaluate', 'tune'])
    p.add_argument('--output-dir', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--sensor', required=True)
    p.add_argument('--targets', default='{}')
    for name in ('speed-kp', 'speed-ki', 'speed-kd', 'dist-kp', 'dist-ki', 'dist-kd'):
        p.add_argument('--' + name)
    a = p.parse_args()
    sim = import_deliverables(a.output_dir)
    config = load_yaml(a.config)
    sensor = sim.load_sensor_data(a.sensor)
    targets = json.loads(a.targets)
    gains_path = os.path.join(a.output_dir, 'tuning_results.yaml')
    if a.action == 'tune':
        sg = {k: _floats(getattr(a, 'speed_' + k)) or SPEED_GRID[k] for k in ('kp', 'ki', 'kd')}
        dg = {k: _floats(getattr(a, 'dist_' + k)) or DIST_GRID[k] for k in ('kp', 'ki', 'kd')}
        gains, metrics, log = grid_search(sim, config, sensor, targets, sg, dg)
        if not gains_in_bounds(gains):
            sys.exit(f'gains out of bounds: {gains}')
        write_gains(gains_path, gains)
        print(json.dumps({'gains': gains, 'metrics': metrics, 'log': log}, indent=2, default=str))
    else:
        gains = load_yaml(gains_path)
        rows = sim.run_simulation(config, sensor, gains)
        print(json.dumps({'gains': gains, 'metrics': compute_metrics(rows, config, targets)}, indent=2, default=str))


if __name__ == '__main__':
    main()
