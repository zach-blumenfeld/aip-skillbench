"""Closed-loop ACC simulation driven by recorded sensor data.

Usage: python simulation.py [--params vehicle_params.yaml] [--sensor sensor_data.csv]
                            [--tuning tuning_results.yaml] [--output simulation_results.csv]
                            [--distance-model integrated|sensor]

Ego speed is simulated from the controller's command (kinematic model, speed >= 0).
The lead vehicle comes from the sensor file (lead_speed/distance empty = no lead).
Distance models:
  integrated    - gap seeded from the sensor distance when a lead is first detected,
                  then propagated: gap += (lead_speed - ego_speed) * dt   (default)
  sensor        - raw sensor distance (open loop; only when the task says so)
Output columns: time, ego_speed, acceleration_cmd, mode, distance_error, distance, ttc
(distance_error/distance/ttc empty when not applicable).
"""
import argparse
import copy
import math
import os
import sys

import pandas as pd
import yaml

from acc_system import AdaptiveCruiseControl

DEFAULTS = {
    'vehicle': {'mass': 1500, 'max_acceleration': 3.0, 'max_deceleration': -8.0,
                'drag_coefficient': 0.3},
    'acc_settings': {'set_speed': 30.0, 'time_headway': 1.5, 'min_distance': 10.0,
                     'emergency_ttc_threshold': 3.0},
    'pid_speed': {'kp': 0.1, 'ki': 0.01, 'kd': 0.0},
    'pid_distance': {'kp': 0.1, 'ki': 0.01, 'kd': 0.0},
    'simulation': {'dt': 0.1},
}
OUTPUT_COLUMNS = ['time', 'ego_speed', 'acceleration_cmd', 'mode',
                  'distance_error', 'distance', 'ttc']
# simulate(..., keep_lead=True) also returns lead_speed (used by metrics, not written).


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_yaml(path):
    """safe_load a YAML file; {} when missing or unparsable (defaults apply)."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"YAML parse error in {path}: {e}", file=sys.stderr)
        return {}


def load_config(params_path, tuning_path=None):
    """vehicle_params.yaml merged over defaults; tuned gains (if any) merged on top."""
    config = _merge(DEFAULTS, load_yaml(params_path))
    tuned = load_yaml(tuning_path)
    for key in ('pid_speed', 'pid_distance'):
        if isinstance(tuned.get(key), dict):
            config[key] = _merge(config[key], tuned[key])
    if config['vehicle']['max_deceleration'] > 0:  # accept a positive magnitude too
        config['vehicle']['max_deceleration'] = -config['vehicle']['max_deceleration']
    return config


def load_sensor(path):
    df = pd.read_csv(path, na_values=['', 'NA', 'null', 'None', 'nan'])
    df.columns = [c.strip() for c in df.columns]
    missing = {'time', 'lead_speed', 'distance'} - set(df.columns)
    if missing:
        raise ValueError(f"sensor file {path} lacks columns {sorted(missing)}")
    return df.sort_values('time').reset_index(drop=True)


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def simulate(config, sensor, distance_model='integrated', initial_speed=None, keep_lead=False):
    """Run the closed loop over every sensor row; return a DataFrame of OUTPUT_COLUMNS."""
    acc = AdaptiveCruiseControl(config)
    times = sensor['time'].astype(float).tolist()
    lead = [_num(v) for v in sensor['lead_speed'].tolist()]
    dist = [_num(v) for v in sensor['distance'].tolist()]
    rec_ego = ([_num(v) or 0.0 for v in sensor['ego_speed'].tolist()]
               if 'ego_speed' in sensor.columns else None)
    cfg_dt = float(config['simulation']['dt'])
    if initial_speed is None:
        initial_speed = rec_ego[0] if rec_ego else 0.0
    ego = float(initial_speed)
    gap = None
    rows = []
    for i, t in enumerate(times):
        dt = times[i + 1] - t if i + 1 < len(times) else cfg_dt
        present = lead[i] is not None and dist[i] is not None
        if not present:
            gap = None
        elif distance_model == 'sensor':
            gap = dist[i]
        elif gap is None:  # integrated: (re)acquire from the sensor on detection
            gap = dist[i]
        accel, mode, d_err = acc.compute(ego, lead[i] if present else None, gap, dt)
        ttc = acc.last_ttc
        rows.append({'time': t, 'ego_speed': ego, 'acceleration_cmd': accel, 'mode': mode,
                     'distance_error': d_err, 'distance': gap if present else None,
                     'ttc': ttc, 'lead_speed': lead[i] if present else None})
        # Kinematic update (vehicle-dynamics): speed then position / gap.
        if present and distance_model == 'integrated':
            gap = gap - (ego - lead[i]) * dt
        ego = max(0.0, ego + accel * dt)
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS + (['lead_speed'] if keep_lead else []))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--params', default='vehicle_params.yaml')
    ap.add_argument('--sensor', default='sensor_data.csv')
    ap.add_argument('--tuning', default='tuning_results.yaml')
    ap.add_argument('--output', default='simulation_results.csv')
    ap.add_argument('--distance-model', default='integrated',
                    choices=['integrated', 'sensor'])
    args = ap.parse_args()
    config = load_config(args.params, args.tuning)
    results = simulate(config, load_sensor(args.sensor), args.distance_model)
    results.to_csv(args.output, index=False)
    counts = results['mode'].value_counts().to_dict()
    print(f"Wrote {len(results)} rows to {args.output}; modes={counts}; "
          f"min distance={results['distance'].min():.2f} m")


if __name__ == '__main__':
    main()
