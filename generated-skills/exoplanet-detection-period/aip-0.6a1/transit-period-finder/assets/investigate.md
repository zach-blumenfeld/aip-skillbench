# Weak or ambiguous transit signal: search by hand

The automated search in {meta.name} did not yield a candidate that passes vetting. You still
owe the task a period: find the best-supported one and write it.

Light curve: {lc_path}
Output file: {output_path}

Task statement:
{task_statement}

What the file looks like:
{data_summary}

What the automated search did:
{search_summary}

Its candidates (rank 1 = highest BLS power):
{candidates}

Work through these, stopping once a candidate passes the validation thresholds
(SDE > 6, depth SNR > 7, >= 2 transits with data, odd/even mismatch < 3 sigma, no secondary
at phase 0.5 comparable to the primary, not a rotation harmonic, stable across windows):

1. Re-check the flag convention. If the summary shows that the kept subset has the larger
   point-to-point scatter, or that most rows were removed, rerun with the other convention.
2. Rerun the search script by hand with overrides. It reads the same JSON on stdin, plus
   optional `window_days`, `min_duration`, `max_duration`, `period_min`, `period_max`:
   run `python scripts/search_transits.py` from the skill folder, piping in a JSON object
   with key `state` holding `lc_path`, `flag_convention`, `data_summary` (as above) and your
   overrides. Try a longer window (residual rotation leaking in) and a shorter one (transit
   being flattened), and a wider duration range (long transits up to 0.4 d for longer periods).
3. Try TLS on the flattened light curve (binned to ~6-10 min for speed, flux_err included),
   with a restricted period range first; see the reference for the call.
4. Check aliases: fold at 0.5x, 1x, 2x the best period and compare odd/even depths and the
   depth at phase 0.5.
5. Refine the winner: mask its transits, re-flatten, and fit (or run
   `python scripts/refine_period.py` with `candidate_rank` / `alias_factor` / `output_path` in
   its state after a manual search_transits run), then write the period, rounded to 5
   decimals, as the only content of {output_path}.

If nothing passes, still write the best-supported period (highest SDE among
candidates that are not rotation harmonics), and say in your notes that it is low confidence.
Never write a period you did not compute from this file.

Answer with:
- `fallback_period_text`: exactly what you wrote to the output file (e.g. "2.44535").
- `investigation_notes`: what you tried, which candidate won and why, and its SDE / SNR /
  transit count.
