"""AIP step: load vehicle params + sensor CSV, report the config and a data profile.

stdin: {"currentState": {"params_path", "sensor_path", ...}, ...}; stdout: one JSON object.
"""
import json
import math
import sys

from simulation import load_config, load_sensor


def segments(times, present):
    out, start = [], None
    for t, p in zip(times + [None], present + [False]):
        if p and start is None:
            start = t
        elif not p and start is not None:
            out.append([start, prev])
            start = None
        prev = t
    return out


def main():
    state = json.load(sys.stdin)['currentState']
    warnings = []
    config = load_config(state['params_path'])
    sensor = load_sensor(state['sensor_path'])
    times = [float(t) for t in sensor['time']]
    steps = [round(b - a, 6) for a, b in zip(times, times[1:])]
    dt_cfg = float(config['simulation']['dt'])
    if steps and max(abs(s - dt_cfg) for s in steps) > 1e-6:
        warnings.append(f"sensor time step varies or differs from simulation.dt={dt_cfg}; "
                        "the simulation uses each row's actual time step")
    present = (sensor['lead_speed'].notna() & sensor['distance'].notna()).tolist()
    partial = int((sensor['lead_speed'].notna() ^ sensor['distance'].notna()).sum())
    if partial:
        warnings.append(f"{partial} rows have only one of lead_speed/distance; treated as no lead")
    lead = sensor.loc[sensor['lead_speed'].notna(), 'lead_speed']
    dist = sensor.loc[sensor['distance'].notna(), 'distance']
    if config['vehicle']['max_deceleration'] >= 0:
        warnings.append("max_deceleration is not negative after loading")
    profile = {
        'rows': len(sensor),
        'columns': list(sensor.columns),
        'time_start': times[0], 'time_end': times[-1],
        'time_step': (sum(steps) / len(steps)) if steps else None,
        'initial_ego_speed': float(sensor['ego_speed'].iloc[0]) if 'ego_speed' in sensor else None,
        'lead_present_rows': int(sum(present)),
        'lead_segments_s': segments(times, present),
        'lead_speed_range': [float(lead.min()), float(lead.max())] if len(lead) else None,
        'sensor_distance_range': [float(dist.min()), float(dist.max())] if len(dist) else None,
        'lead_faster_than_set_speed_rows': int((lead > float(config['acc_settings']['set_speed'])).sum()),
    }
    if profile['sensor_distance_range'] and profile['sensor_distance_range'][0] < config['acc_settings']['min_distance']:
        warnings.append("recorded sensor distance drops below min_distance (it was recorded with a "
                        "different ego trajectory); a closed-loop simulation must propagate the gap "
                        "from its own ego speed, not copy the recorded distance")
    print(json.dumps({'config': config, 'data_profile': profile, 'input_warnings': warnings}))


if __name__ == '__main__':
    main()
