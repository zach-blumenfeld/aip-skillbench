"""Step profile_inputs: validate the task's config + sensor files and profile the drive."""
import json
import math
import os
import sys

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

import pandas as pd
import yaml

from acc_common import merged_targets

REQUIRED_CONFIG = {
    'vehicle': ['max_acceleration', 'max_deceleration'],
    'acc_settings': ['set_speed', 'time_headway', 'min_distance', 'emergency_ttc_threshold'],
}
# instruction constraint name -> (config section, key)
CONSTRAINT_MAP = {
    'set_speed': ('acc_settings', 'set_speed'),
    'max_acceleration': ('vehicle', 'max_acceleration'),
    'max_deceleration': ('vehicle', 'max_deceleration'),
    'time_headway': ('acc_settings', 'time_headway'),
    'min_distance': ('acc_settings', 'min_distance'),
    'emergency_ttc_threshold': ('acc_settings', 'emergency_ttc_threshold'),
    'dt': ('simulation', 'dt'),
}


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def main():
    state = json.load(sys.stdin)['state']
    config_path, sensor_path = state['config_path'], state['sensor_path']
    targets = merged_targets(state.get('targets'))
    constraints = state.get('constraints') or {}
    issues = []

    for p in (config_path, sensor_path):
        if not os.path.isfile(p):
            fail(f'input file not found: {p}')
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        fail(f'YAML parse error in {config_path}: {e}')
    missing = [f'{sec}.{k}' for sec, keys in REQUIRED_CONFIG.items() for k in keys
               if k not in (config.get(sec) or {})]
    if missing:
        fail(f'{config_path} lacks required keys {missing}; AdaptiveCruiseControl reads them as config[section][key]')
    if 'simulation' not in config or 'dt' not in (config.get('simulation') or {}):
        issues.append('config has no simulation.dt; the simulation falls back to dt=0.1 s')
    for loop in ('pid_speed', 'pid_distance'):
        if loop not in config:
            issues.append(f'config has no {loop} block; initial gains default to kp=0.1, ki=0.01, kd=0')

    df = pd.read_csv(sensor_path, na_values=['', 'NA', 'null'])
    cols = df.columns.tolist()
    need = ['time', 'lead_speed', 'distance']
    if any(c not in cols for c in need):
        fail(f'{sensor_path} columns {cols} lack {[c for c in need if c not in cols]}')
    if 'ego_speed' not in cols:
        issues.append('sensor data has no ego_speed column; initial ego speed defaults to 0')

    dt_cfg = float((config.get('simulation') or {}).get('dt', 0.1))
    t = df['time'].astype(float).tolist()
    steps = [round(b - a, 9) for a, b in zip(t, t[1:])]
    dt_data = float(pd.Series(steps).median()) if steps else None
    if dt_data is not None and abs(dt_data - dt_cfg) > 1e-6:
        issues.append(f'sensor time step {dt_data} s differs from config dt {dt_cfg} s')
    if steps and (max(steps) - min(steps)) > 1e-6:
        issues.append(f'sensor time steps are irregular (min {min(steps)}, max {max(steps)})')
    expected_rows = int(round(targets['duration_s'] / dt_cfg)) + 1
    if len(df) != expected_rows:
        issues.append(f'sensor data has {len(df)} rows; a {targets["duration_s"]} s run at dt={dt_cfg} needs {expected_rows}')

    present = (df['lead_speed'].notna() & df['distance'].notna()).tolist()
    half = df['lead_speed'].notna() ^ df['distance'].notna()
    if half.any():
        issues.append(f'{int(half.sum())} rows have only one of lead_speed/distance; treated as no lead vehicle')
    segments, start = [], 0
    for i in range(1, len(present) + 1):
        if i == len(present) or present[i] != present[start]:
            segments.append({'lead_present': bool(present[start]), 'start_s': t[start], 'end_s': t[i - 1]})
            start = i
    dist = df['distance']
    jumps = df.loc[dist.diff().abs() > 10.0, 'time'].tolist()
    ego0 = float(df['ego_speed'].iloc[0]) if 'ego_speed' in cols and pd.notna(df['ego_speed'].iloc[0]) else 0.0

    set_speed = float(config['acc_settings']['set_speed'])
    a_max = float(config['vehicle']['max_acceleration'])
    min_rise = 0.8 * set_speed / a_max if a_max > 0 else math.inf
    if min_rise >= targets['rise_time_max_s']:
        issues.append(f'rise-time target {targets["rise_time_max_s"]} s is infeasible: 10->90% of {set_speed} m/s '
                      f'at {a_max} m/s^2 takes at least {min_rise:.2f} s')

    for name, value in constraints.items():
        if name == 'initial_speed':
            if abs(float(value) - ego0) > 0.5:
                issues.append(f'instruction initial speed {value} m/s but sensor ego_speed starts at {ego0}')
            continue
        if name not in CONSTRAINT_MAP:
            continue
        sec, key = CONSTRAINT_MAP[name]
        cfg_val = (config.get(sec) or {}).get(key)
        if cfg_val is None or abs(float(cfg_val) - float(value)) > 1e-9:
            issues.append(f'instruction says {name}={value} but config {sec}.{key}={cfg_val}; the config value is used')

    profile = {
        'rows': len(df),
        'expected_rows': expected_rows,
        'time_span_s': [t[0], t[-1]] if t else None,
        'dt_config_s': dt_cfg,
        'dt_data_s': dt_data,
        'initial_ego_speed': ego0,
        'lead_segments': segments,
        'lead_present_s': round(sum(present) * dt_cfg, 3),
        'sensor_distance_jumps_at_s': jumps,
        'sensor_min_distance': float(dist.min()) if dist.notna().any() else None,
        'lead_speed_range': [float(df['lead_speed'].min()), float(df['lead_speed'].max())] if df['lead_speed'].notna().any() else None,
        'config': config,
        'min_feasible_rise_time_s': round(min_rise, 3),
        'targets': targets,
    }
    print(json.dumps({'input_profile': profile, 'input_issues': issues}))


if __name__ == '__main__':
    main()
