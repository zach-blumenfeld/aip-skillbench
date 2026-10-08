"""AIP step: grid-search speed/distance PID gains and write the tuning YAML.

Reads params_path, sensor_path, targets, distance_model, tuning_output_path from
currentState. Writes {pid_speed: {kp, ki, kd}, pid_distance: {kp, ki, kd}} to
tuning_output_path (the original params file is never modified).
"""
import json
import sys

import yaml

from simulation import load_config, load_sensor
from tune import tune


def main():
    state = json.load(sys.stdin)['currentState']
    config = load_config(state['params_path'])
    sensor = load_sensor(state['sensor_path'])
    result = tune(config, sensor, state['targets'], state.get('distance_model', 'integrated'))
    gains = {'pid_speed': {k: float(v) for k, v in result['pid_speed'].items()},
             'pid_distance': {k: float(v) for k, v in result['pid_distance'].items()}}
    with open(state['tuning_output_path'], 'w') as f:
        yaml.dump(gains, f, default_flow_style=False, sort_keys=False)
    print(json.dumps({'tuned_gains': gains, 'tuning_scorecard': result['scorecard'],
                      'tuning_path': state['tuning_output_path']}, default=str))


if __name__ == '__main__':
    main()
