"""AIP step: check the deliverable results CSV structurally and against the targets.

Reads results_path, sensor_path, params_path, tuning_path, targets, distance_model,
expected_columns and column_map ({task column name: reference column name}, for tasks that
rename columns) from currentState. Emits verification + all_pass. Fails when the reference
columns needed for scoring cannot be found, so a renamed CSV never passes vacuously.
"""
import json
import math
import os
import sys

import pandas as pd

from metrics import scorecard
from simulation import OUTPUT_COLUMNS, load_config, load_sensor, simulate

MODES = {'cruise', 'follow', 'emergency'}


def main():
    state = json.load(sys.stdin)['currentState']
    problems, notes = [], []
    path = state['results_path']
    if not os.path.exists(path):
        print(json.dumps({'verification': {'problems': [f"{path} does not exist"]}, 'all_pass': False}))
        return
    df = pd.read_csv(path)
    sensor = load_sensor(state['sensor_path'])
    config = load_config(state['params_path'], state.get('tuning_path'))
    expected = state.get('expected_columns') or OUTPUT_COLUMNS
    if list(df.columns) != list(expected):
        problems.append(f"columns {list(df.columns)} != expected {list(expected)}")
    column_map = {k: v for k, v in (state.get('column_map') or {}).items() if v}
    df = df.rename(columns=column_map)
    needed = {'time', 'ego_speed', 'acceleration_cmd', 'mode'}
    if state['targets'].get('distance_ss_error_max') is not None:
        needed.add('distance_error')
    if state['targets'].get('min_distance_min') is not None:
        needed.add('distance')
    absent = sorted(needed - set(df.columns))
    if absent:
        problems.append(f"cannot verify: no column maps to reference column(s) {absent}; set "
                        "column_map {task column: reference column} or add the columns")
    if len(df) != len(sensor):
        problems.append(f"{len(df)} rows but sensor file has {len(sensor)} (one output row per sensor row)")
    elif 'time' in df and (df['time'].astype(float).values - sensor['time'].astype(float).values).__abs__().max() > 1e-6:
        problems.append("time column does not match the sensor time grid")
    if 'mode' in df:
        bad = set(df['mode'].dropna().unique()) - MODES
        if bad:
            problems.append(f"unknown mode labels {sorted(bad)}; use exactly {sorted(MODES)}")
    lo = float(config['vehicle']['max_deceleration'])
    hi = float(config['vehicle']['max_acceleration'])
    if 'acceleration_cmd' in df:
        a = df['acceleration_cmd'].astype(float)
        if a.isna().any():
            problems.append("acceleration_cmd has empty values")
        if a.min() < lo - 1e-9 or a.max() > hi + 1e-9:
            problems.append(f"acceleration_cmd outside [{lo}, {hi}]: [{a.min()}, {a.max()}]")
    if 'ego_speed' in df:
        if (df['ego_speed'] < -1e-9).any():
            problems.append("negative ego_speed")
        if 'ego_speed' in sensor and len(df) == len(sensor) and \
                (df['ego_speed'].values - sensor['ego_speed'].fillna(0).values).__abs__().max() < 1e-9:
            problems.append("ego_speed is a copy of the recorded sensor ego_speed; it must be simulated")
    if {'mode', 'distance'} <= set(df.columns):
        cruise_with_dist = int((df['mode'].eq('cruise') & df['distance'].notna()).sum())
        if cruise_with_dist:
            notes.append(f"{cruise_with_dist} cruise rows carry a distance value")

    # Reference reproduction: the pack's simulate() with the same gains.
    ref = simulate(config, sensor, state.get('distance_model', 'integrated'), keep_lead=True)
    if len(df) == len(ref) and 'ego_speed' in df:
        diff = float((df['ego_speed'].values - ref['ego_speed'].values).__abs__().max())
        if diff > 1e-6:
            notes.append(f"deliverable ego_speed differs from the pack reference by up to {diff:.4g} m/s; "
                         "fine if the task required different logic, otherwise look for a porting bug")

    scored = df.copy()
    if len(df) == len(sensor):
        scored['lead_speed'] = [None if (isinstance(v, float) and math.isnan(v)) else v
                                for v in sensor['lead_speed'].tolist()]
    for col in ('distance_error', 'distance'):
        if col in scored:
            scored[col] = scored[col].astype(float)
        else:
            scored[col] = float('nan')  # not delivered and not graded (checked above)
    card = scorecard(scored, float(config['acc_settings']['set_speed']), state['targets']) \
        if not absent and len(df) == len(sensor) else {}
    if card and not card['all_pass']:
        problems += [f"target missed: {k} = {v['value']} (needs {v['limit']})"
                     for k, v in card['checks'].items() if not v['pass']]
    print(json.dumps({'verification': {'problems': problems, 'notes': notes, 'scorecard': card},
                      'all_pass': not problems}, default=str))


if __name__ == '__main__':
    main()
