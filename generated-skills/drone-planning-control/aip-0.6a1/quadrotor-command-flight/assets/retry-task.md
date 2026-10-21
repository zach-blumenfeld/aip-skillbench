Some flight commands failed in `{meta.name}`. Failed labels: {failed}

Full per-command report (each entry: label, command, status, mode, profiles,
min_feasible_durations, plan_feasible, accel peaks, metrics, max_pos_err, criteria, gains,
unparsed_lines):

{report}

For every failed label, decide the cause from its report entry and write one retry entry.

1. `status: "unparsed"` — the line matched none of the four command forms. Rewrite it to
   the canonical form with exactly the same numbers and meaning, e.g. "Climb to 2 m in 4 s"
   → "Take off to 2 m height in 4 seconds", "Descend from 2 m height within 4 sec"
   → "Land from 2 m height in 4 seconds", "Go from (0,0,1) to (1,0,1) in 2 seconds" →
   "Fly from (0,0,1) to (1,0,1) in 2 seconds", "Hold 1.5 m altitude for 6 s" → "Hover at
   1.5 m height for 6 seconds". Never invent numbers; if the line has no usable
   height/duration (or coordinates), set `skip_reason` instead.
2. `plan_feasible: false` or `criteria.accel_limits: false` — the commanded time is too
   short for the acceleration limits even with the trapezoidal profile. Gains cannot fix
   this. Set `skip_reason` stating the limit that is violated and the segment's
   `min_feasible_durations` value; do not change the command's numbers.
3. Simulated but `tracking`, `steady_state`, or `overshoot` false — a tuning failure.
   Read `max_pos_err`, the metrics, and the gains that were tried, apply the tuning table
   in the reference, and give a new six-key `gains` base (each a list of 3 floats). The
   retry searches a wide grid around it.

Answer with `retry_spec`: an object keyed by failed label; each value is an object with
three keys: `command` (canonical text, or null to reuse the file), `gains` (six-key gain
object, or null for the default base), `skip_reason` (string, or null to retry).
