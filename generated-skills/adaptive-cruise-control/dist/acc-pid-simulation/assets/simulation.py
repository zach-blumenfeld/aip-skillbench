"""ACC vehicle simulation driven by recorded lead-vehicle data.

Requires: Python >= 3.8, pandas, pyyaml; acc_system.py and pid_controller.py
in the same folder.

Usage:
    python3 simulation.py [--config vehicle_params.yaml] [--sensor sensor_data.csv]
                          [--gains tuning_results.yaml] [--output simulation_results.csv]
Relative paths resolve against this file's folder first, then the cwd.

PID gains are read from tuning_results.yaml at runtime (no tuning here).
The ego vehicle is simulated (kinematic model) from the first ego_speed in the
sensor file; the sensor's lead_speed drives the lead vehicle. The gap is
seeded from the sensor distance when a lead first appears (or reappears after
a no-lead stretch) and then integrated:
    distance += (lead_speed - ego_speed) * dt
because the recorded distance belongs to the recorded ego trajectory, not the
simulated one. Each output row holds the state at that time and the command
computed from it; ego_speed is then advanced: v = max(0, v + a*dt).
"""

import argparse
import math
import os
import sys

import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from acc_system import AdaptiveCruiseControl  # noqa: E402

COLUMNS = ['time', 'ego_speed', 'acceleration_cmd', 'mode', 'distance_error', 'distance', 'ttc']


def resolve(path):
    if os.path.isabs(path):
        return path
    here = os.path.join(HERE, path)
    cwd = os.path.abspath(path)
    return cwd if (not os.path.exists(here) and os.path.exists(cwd)) else here


def load_yaml(path):
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        sys.exit(f"ERROR: {path} not found")
    except yaml.YAMLError as e:
        sys.exit(f"ERROR: cannot parse {path}: {e}")


def _num(x):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def run_simulation(config, sensor, gains=None):
    """Simulate every sensor row; return a DataFrame with COLUMNS."""
    cfg = dict(config)
    if gains:
        for key in ('pid_speed', 'pid_distance'):
            if key in gains:
                cfg[key] = gains[key]
    dt_cfg = _num((cfg.get('simulation') or {}).get('dt'))
    acc = AdaptiveCruiseControl(cfg)

    times = sensor['time'].astype(float).tolist()
    leads = [_num(v) for v in sensor['lead_speed'].tolist()]
    dists = [_num(v) for v in sensor['distance'].tolist()]
    ego = _num(sensor['ego_speed'].iloc[0]) if 'ego_speed' in sensor else None
    ego = 0.0 if ego is None else max(0.0, ego)

    rows = []
    gap = None
    for i, t in enumerate(times):
        if i + 1 < len(times):
            dt = times[i + 1] - times[i]
        else:
            dt = dt_cfg if dt_cfg else (times[i] - times[i - 1] if i else 0.1)
        lead = leads[i]
        present = lead is not None and dists[i] is not None
        if not present:
            gap = None
        elif gap is None:
            gap = dists[i]  # new lead: seed from the sensor
        # else: gap already advanced at the end of the previous step

        accel, mode, d_err = acc.compute(ego, lead if present else None, gap, dt)
        ttc = acc.time_to_collision(gap, ego, lead) if present else None
        rows.append({
            'time': _r(t, 3), 'ego_speed': _r(ego), 'acceleration_cmd': _r(accel),
            'mode': mode, 'distance_error': _r(d_err), 'distance': _r(gap) if present else None,
            'ttc': _r(ttc),
        })

        if present:
            gap = gap + (lead - ego) * dt
        ego = max(0.0, ego + accel * dt)

    return pd.DataFrame(rows, columns=COLUMNS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--config', default='vehicle_params.yaml')
    ap.add_argument('--sensor', default='sensor_data.csv')
    ap.add_argument('--gains', default='tuning_results.yaml')
    ap.add_argument('--output', default='simulation_results.csv')
    args = ap.parse_args(argv)

    config = load_yaml(resolve(args.config))
    gains = load_yaml(resolve(args.gains))
    for key in ('pid_speed', 'pid_distance'):
        if not all(k in (gains.get(key) or {}) for k in ('kp', 'ki', 'kd')):
            sys.exit(f"ERROR: {args.gains} lacks {key}.kp/ki/kd")
    sensor_path = resolve(args.sensor)
    if not os.path.exists(sensor_path):
        sys.exit(f"ERROR: {sensor_path} not found")
    sensor = pd.read_csv(sensor_path, na_values=['', 'NA', 'null', 'None', 'nan'])
    missing = {'time', 'lead_speed', 'distance'} - set(sensor.columns)
    if missing:
        sys.exit(f"ERROR: sensor file lacks columns {sorted(missing)}; has {sensor.columns.tolist()}")

    df = run_simulation(config, sensor, gains)
    out = args.output if os.path.isabs(args.output) else os.path.join(HERE, args.output)
    df.to_csv(out, index=False)
    print(f"wrote {out}: {len(df)} rows; modes {df['mode'].value_counts().to_dict()}")


if __name__ == '__main__':
    main()
