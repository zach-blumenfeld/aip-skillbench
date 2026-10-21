"""Step build_and_tune: write the ACC modules into the output dir, grid-search the PID gains
against the sensor data, and write tuning_results.yaml."""
import json
import os
import sys

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

from acc_common import gains_in_bounds, grid_search, import_deliverables, load_yaml, write_gains

DELIVERABLES = {'pid_controller': 'pid_controller.py', 'acc_system': 'acc_system.py', 'simulation': 'simulation.py'}


def main():
    payload = json.load(sys.stdin)
    state, assets = payload['state'], payload['assets']
    out = state['output_dir']
    os.makedirs(out, exist_ok=True)
    for stem, filename in DELIVERABLES.items():
        if stem not in assets:
            sys.exit(f'asset {stem} missing from the step payload')
        with open(os.path.join(out, filename), 'w') as f:
            f.write(assets[stem])

    sim = import_deliverables(out)
    config = load_yaml(state['config_path'])
    sensor = sim.load_sensor_data(state['sensor_path'])
    gains, metrics, log = grid_search(sim, config, sensor, state.get('targets') or {})
    if not gains_in_bounds(gains):
        sys.exit(f'search produced out-of-bounds gains {gains}')
    write_gains(os.path.join(out, 'tuning_results.yaml'), gains)
    print(json.dumps({
        'tuned_gains': gains,
        'tuning_metrics': metrics,
        'tuning_log': log,
        'targets_met': bool(metrics['targets_met']),
    }, default=float))


if __name__ == '__main__':
    main()
