"""Step simulate_and_report: run the delivered simulation.py (gains from tuning_results.yaml),
verify simulation_results.csv, compute the metrics, and write acc_report.md."""
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__
from string import Template

import pandas as pd

from acc_common import GAIN_BOUNDS, SETTLE_WINDOW_S, compute_metrics, gains_in_bounds, load_yaml, merged_targets

COLUMNS = ['time', 'ego_speed', 'acceleration_cmd', 'mode', 'distance_error', 'distance', 'ttc']
FILES = ['pid_controller.py', 'acc_system.py', 'simulation.py', 'tuning_results.yaml',
         'simulation_results.csv', 'acc_report.md']


def fmt(v, nd=3, unit=''):
    if v is None:
        return 'n/a'
    return f'{v:.{nd}f}{unit}'


def main():
    payload = json.load(sys.stdin)
    state, assets = payload['state'], payload['assets']
    out = state['output_dir']
    targets = merged_targets(state.get('targets'))
    profile = state['input_profile']
    config = load_yaml(state['config_path'])
    csv_path = os.path.join(out, 'simulation_results.csv')
    gains_path = os.path.join(out, 'tuning_results.yaml')

    gains = load_yaml(gains_path)
    if not gains_in_bounds(gains):
        sys.exit(f'{gains_path} gains outside kp (0,10), ki [0,5), kd [0,5): {gains}')

    proc = subprocess.run([sys.executable, 'simulation.py', '--config', os.path.abspath(state['config_path']),
                           '--sensor', os.path.abspath(state['sensor_path']), '--gains', gains_path,
                           '--output', csv_path], cwd=out, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f'simulation.py failed:\n{proc.stderr}')

    df = pd.read_csv(csv_path)
    rows = [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict('records')]
    sensor = pd.read_csv(state['sensor_path'])
    a_min, a_max = float(config['vehicle']['max_deceleration']), float(config['vehicle']['max_acceleration'])
    cruise = df['mode'] == 'cruise'
    checks = {
        'columns_exact': df.columns.tolist() == COLUMNS,
        'row_count_matches_sensor': len(df) == len(sensor),
        'row_count_matches_duration': len(df) == profile['expected_rows'],
        'time_matches_sensor': bool((df['time'].round(6).values == sensor['time'].round(6).values).all()) if len(df) == len(sensor) else False,
        'modes_valid': bool(df['mode'].isin(['cruise', 'follow', 'emergency']).all()),
        'cruise_rows_blank_distance_fields': bool(df.loc[cruise, ['distance_error', 'distance', 'ttc']].isna().all().all()),
        'accel_within_limits': bool(df['acceleration_cmd'].between(a_min - 1e-9, a_max + 1e-9).all()),
        'ego_speed_nonnegative': bool((df['ego_speed'] >= 0).all()),
        'gains_in_bounds': True,
    }
    # Re-running must reproduce the file byte for byte (gains are read from yaml, no hidden tuning).
    rerun = subprocess.run([sys.executable, 'simulation.py', '--config', os.path.abspath(state['config_path']),
                            '--sensor', os.path.abspath(state['sensor_path']), '--gains', gains_path,
                            '--output', csv_path + '.rerun'], cwd=out, capture_output=True, text=True)
    checks['deterministic_rerun'] = rerun.returncode == 0 and open(csv_path).read() == open(csv_path + '.rerun').read()
    if os.path.exists(csv_path + '.rerun'):
        os.remove(csv_path + '.rerun')

    m = compute_metrics(rows, config, targets)
    tuned = state['tuned_gains']
    manual = any(abs(float(gains[l][k]) - float(tuned[l][k])) > 1e-12 for l in tuned for k in ('kp', 'ki', 'kd'))
    acc = config['acc_settings']

    def verdict(name):
        return 'PASS' if m['checks'][name] else 'FAIL'

    seg_lines = '\n'.join(f"| {s['start_s']:.1f}-{s['end_s']:.1f} s | {'lead vehicle' if s['lead_present'] else 'no lead'} |"
                          for s in profile['lead_segments'])
    log_lines = '\n'.join(f"- Stage `{e['stage']}`: {e['evaluated']} gain sets simulated, best "
                          f"kp={e['best']['kp']}, ki={e['best']['ki']}, kd={e['best']['kd']} (cost {e['cost']})"
                          for e in state['tuning_log'])
    issues = state.get('input_issues') or []
    values = {
        'set_speed': acc['set_speed'], 'time_headway': acc['time_headway'], 'min_distance': acc['min_distance'],
        'ttc': acc['emergency_ttc_threshold'], 'a_max': a_max, 'a_min': a_min, 'dt': profile['dt_config_s'],
        'rows': len(df), 'duration': targets['duration_s'],
        'ks_kp': gains['pid_speed']['kp'], 'ks_ki': gains['pid_speed']['ki'], 'ks_kd': gains['pid_speed']['kd'],
        'kd_kp': gains['pid_distance']['kp'], 'kd_ki': gains['pid_distance']['ki'], 'kd_kd': gains['pid_distance']['kd'],
        'tuning_log': log_lines,
        'manual_note': ('The gains in tuning_results.yaml were adjusted by hand after the grid search; the '
                        'metrics below are for the final file.' if manual else
                        'The final gains are the grid-search optimum.'),
        'segments': seg_lines,
        'rise': fmt(m['rise_time_s'], 2, ' s'), 'rise_t': targets['rise_time_max_s'], 'rise_v': verdict('rise_time'),
        'os': fmt(m['overshoot_pct'], 2, ' %'), 'os_t': targets['overshoot_max_pct'], 'os_v': verdict('overshoot'),
        'sse': fmt(m['speed_ss_error'], 3, ' m/s'), 'sse_t': targets['speed_ss_error_max'], 'sse_v': verdict('speed_ss_error'),
        'dse': fmt(m['distance_ss_error'], 3, ' m'), 'dse_t': targets['distance_ss_error_max'], 'dse_v': verdict('distance_ss_error'),
        'mind': fmt(m['min_distance'], 2, ' m'), 'mind_t': targets['min_distance_min'], 'mind_v': verdict('min_distance'),
        'settle': fmt(m['settling_time_2pct_s'], 1, ' s'), 'minttc': fmt(m['min_ttc_s'], 2, ' s'),
        'dse_max': fmt(m['distance_ss_error_max'], 3, ' m'), 'dse_rows': m['distance_ss_rows'],
        'dse_all': fmt(m['distance_error_mean_abs_all_follow'], 2, ' m'), 'settle_window': SETTLE_WINDOW_S,
        't_cruise': m['mode_time_s']['cruise'], 't_follow': m['mode_time_s']['follow'],
        't_emerg': m['mode_time_s']['emergency'], 'n_emerg': m['emergency_events'],
        'accel_lo': fmt(m['accel_range'][0], 2), 'accel_hi': fmt(m['accel_range'][1], 2),
        'overall': 'All performance targets are met.' if m['targets_met'] else
                   'Not all targets are met: ' + ', '.join(k for k, v in m['checks'].items() if not v) + '.',
        'issues': '\n'.join(f'- {i}' for i in issues) if issues else '- None.',
        'bounds': ', '.join(f'{k} {lo}..{hi}' for k, (lo, hi) in GAIN_BOUNDS.items()),
    }
    with open(os.path.join(out, 'acc_report.md'), 'w') as f:
        f.write(Template(assets['acc_report_template']).substitute(values))

    missing = [fn for fn in FILES if not os.path.isfile(os.path.join(out, fn))]
    checks['all_deliverables_present'] = not missing
    if not all(checks.values()):
        sys.exit(f'deliverable verification failed: {[k for k, v in checks.items() if not v]}; missing={missing}')
    print(json.dumps({'final_metrics': m, 'verification': checks,
                      'deliverables': [os.path.join(out, fn) for fn in FILES]}, default=float))


if __name__ == '__main__':
    main()
