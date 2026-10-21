"""150 s ACC simulation driven by recorded lead-vehicle data.

Gains are read from tuning_results.yaml at runtime (no tuning happens here).
Lead vehicle data (lead_speed, distance) come from sensor_data.csv; the ego vehicle
is simulated with a kinematic model, and the gap is propagated from the simulated ego
speed and the recorded lead speed, initialised from the sensor distance whenever a
lead vehicle is (re)acquired.
"""
import argparse
import copy
import math
import os

import pandas as pd
import yaml

from acc_system import AdaptiveCruiseControl, time_to_collision

HERE = os.path.dirname(os.path.abspath(__file__))
COLUMNS = ['time', 'ego_speed', 'acceleration_cmd', 'mode', 'distance_error', 'distance', 'ttc']


def load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def load_sensor_data(path):
    df = pd.read_csv(path, na_values=['', 'NA', 'null'])
    missing = [c for c in ('time', 'lead_speed', 'distance') if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns {missing}; found {df.columns.tolist()}")
    return df


def _value(x):
    return None if x is None or pd.isna(x) else float(x)


def _round(x, nd=6):
    return None if x is None else round(float(x), nd)


def run_simulation(config, sensor, gains=None):
    """Simulate one run; returns a list of row dicts in COLUMNS order."""
    config = copy.deepcopy(config)
    if gains:
        config['pid_speed'] = dict(gains['pid_speed'])
        config['pid_distance'] = dict(gains['pid_distance'])
    dt = float(config.get('simulation', {}).get('dt', 0.1))
    acc = AdaptiveCruiseControl(config)

    records = sensor.to_dict('records') if hasattr(sensor, 'to_dict') else list(sensor)
    first_ego = _value(records[0].get('ego_speed')) if records else None
    ego_speed = first_ego if first_ego is not None else 0.0
    gap = None
    results = []
    for rec in records:
        lead_speed = _value(rec.get('lead_speed'))
        measured = _value(rec.get('distance'))
        if lead_speed is None or measured is None:
            lead_speed, gap = None, None
        elif gap is None:
            gap = measured  # lead (re)acquired: start from the measured gap

        accel, mode, distance_error = acc.compute(ego_speed, lead_speed, gap, dt)
        ttc = time_to_collision(gap, ego_speed, lead_speed) if gap is not None else None
        results.append({
            'time': round(float(rec['time']), 6),
            'ego_speed': _round(ego_speed),
            'acceleration_cmd': _round(accel),
            'mode': mode,
            'distance_error': _round(distance_error),
            'distance': _round(gap),
            'ttc': _round(ttc),
        })

        if gap is not None:
            gap = gap - (ego_speed - lead_speed) * dt
        ego_speed = max(0.0, ego_speed + accel * dt)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=os.path.join(HERE, 'vehicle_params.yaml'))
    parser.add_argument('--sensor', default=os.path.join(HERE, 'sensor_data.csv'))
    parser.add_argument('--gains', default=os.path.join(HERE, 'tuning_results.yaml'))
    parser.add_argument('--output', default=os.path.join(HERE, 'simulation_results.csv'))
    args = parser.parse_args(argv)

    config = load_yaml(args.config)
    gains = load_yaml(args.gains)
    sensor = load_sensor_data(args.sensor)
    results = run_simulation(config, sensor, gains)
    pd.DataFrame(results, columns=COLUMNS).to_csv(args.output, index=False)

    modes = pd.Series([r['mode'] for r in results]).value_counts().to_dict()
    gaps = [r['distance'] for r in results if r['distance'] is not None]
    print(f"Wrote {len(results)} rows to {args.output}; modes={modes}; "
          f"min distance={min(gaps) if gaps else 'n/a'}")


if __name__ == '__main__':
    main()
