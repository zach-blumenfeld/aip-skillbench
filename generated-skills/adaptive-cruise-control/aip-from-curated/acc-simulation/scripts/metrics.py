"""Control performance metrics (simulation-metrics) and the ACC scorecard."""
import math


def rise_time(times, values, target):
    """Time from 10% to 90% of target (None if never reached)."""
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
    """|target - mean of the final fraction of the data|."""
    n = len(values)
    start = int(n * (1 - final_fraction))
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


def _runs(modes, wanted):
    """Contiguous index ranges where mode == wanted."""
    runs, start = [], None
    for i, m in enumerate(list(modes) + [None]):
        if m == wanted and start is None:
            start = i
        elif m != wanted and start is not None:
            runs.append((start, i))
            start = None
    return runs


def _steady_follow_error(df, set_speed, settle_s=10.0, window_s=2.5, tol=0.5):
    times = df['time'].tolist()
    modes = df['mode'].tolist()
    errs = df['distance_error'].tolist()
    lead = df['lead_speed'].tolist() if 'lead_speed' in df.columns else None
    dt = (times[-1] - times[0]) / max(len(times) - 1, 1)
    w = max(1, int(round(window_s / dt)))
    picked = []
    entered = None
    for i, m in enumerate(modes):
        if m != 'follow':
            entered = None
            continue
        if entered is None:
            entered = times[i]
        e = errs[i]
        if e is None or math.isnan(e) or times[i] - entered < settle_s:
            continue
        if lead is not None:
            if i < w or i + w > len(lead):
                continue
            before = [x for x in lead[i - w:i] if x == x]
            after = [x for x in lead[i:i + w] if x == x]
            if not before or not after:
                continue
            mb, ma = sum(before) / len(before), sum(after) / len(after)
            if abs(ma - mb) >= tol or ma >= set_speed:
                continue
        picked.append(abs(e))
    return sum(picked) / len(picked) if picked else None


def scorecard(df, set_speed, targets):
    """Compute every metric the ACC task family grades, with pass/fail per target.

    Speed metrics use the initial cruise run (start -> first lead detection).
    Distance steady-state error (the graded value) = mean |distance_error| over
    steady follow rows: follow mode, >= 10 s after entering follow, lead slower
    than set_speed (otherwise the gap cannot be held), and lead speed steady
    (2.5 s means before/after differ < 0.5 m/s). Variants are reported too:
    the simulation-metrics steady_state_error over the final 10% of all follow
    rows, the worst follow run, and the plain mean |error| in follow mode.
    """
    times = df['time'].tolist()
    speeds = df['ego_speed'].tolist()
    modes = df['mode'].tolist()
    out = {}
    cruise = _runs(modes, 'cruise')
    if cruise and cruise[0][0] == 0:
        a, b = cruise[0]
        ct, cv = times[a:b], speeds[a:b]
        out['speed_rise_time_s'] = rise_time(ct, cv, set_speed)
        out['speed_overshoot_pct'] = overshoot_percent(cv, set_speed)
        out['speed_steady_state_error'] = steady_state_error(cv, set_speed)
        out['speed_settling_time_s'] = settling_time(ct, cv, set_speed)
    out['overall_overshoot_pct'] = overshoot_percent(speeds, set_speed)
    follow_err = [e for e, m in zip(df['distance_error'].tolist(), modes)
                  if m == 'follow' and e is not None and not math.isnan(e)]
    if follow_err:
        out['distance_steady_state_error'] = _steady_follow_error(df, set_speed)
        out['distance_ss_error_final10pct_follow'] = steady_state_error(follow_err, 0.0)
        out['distance_mean_abs_error'] = sum(abs(e) for e in follow_err) / len(follow_err)
        per_run = []
        for a, b in _runs(modes, 'follow'):
            errs = [e for e in df['distance_error'].tolist()[a:b] if e is not None and not math.isnan(e)]
            if errs and times[b - 1] - times[a] >= 5.0:
                per_run.append(steady_state_error(errs, 0.0))
        out['distance_ss_error_worst_run'] = max(per_run) if per_run else None
    dist = [d for d in df['distance'].tolist() if d is not None and not math.isnan(d)]
    out['min_distance'] = min(dist) if dist else None
    out['mode_counts'] = {m: modes.count(m) for m in sorted(set(modes))}
    out['rows'] = len(df)
    acc = df['acceleration_cmd'].tolist()
    out['accel_min'], out['accel_max'] = min(acc), max(acc)

    checks = {}
    def check(name, value, limit, op):
        if limit is None:
            return
        ok = value is not None and (value < limit if op == '<' else value > limit)
        checks[name] = {'value': value, 'limit': f"{op} {limit}", 'pass': bool(ok)}
    check('speed_rise_time_s', out.get('speed_rise_time_s'), targets.get('rise_time_max'), '<')
    check('speed_overshoot_pct', out.get('speed_overshoot_pct'), targets.get('overshoot_pct_max'), '<')
    check('speed_steady_state_error', out.get('speed_steady_state_error'), targets.get('speed_ss_error_max'), '<')
    check('distance_steady_state_error', out.get('distance_steady_state_error'), targets.get('distance_ss_error_max'), '<')
    check('min_distance', out.get('min_distance'), targets.get('min_distance_min'), '>')
    out['checks'] = checks
    out['all_pass'] = all(c['pass'] for c in checks.values())
    return out
