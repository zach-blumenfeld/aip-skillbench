# Investigate a weak or suspicious transit candidate ({meta.name})

The broad search did not produce a credible candidate. Task: {task_request}

- Light curve: `{lc_path}`
- Current candidate period: {candidate_period} d
- Preprocessing summary: {prep_summary}
- Search summary (TLS, BLS cross-check, alias checks, vet flags): {search_summary}

Diagnose why, try targeted fixes, and hand the best candidate to refinement.

1. Read the vet flags and look at the PNGs listed in `plots` (prepare.png, search.png).
   Load `references/validation-troubleshooting.md` for the failure catalogue.
2. Re-run the pack's scripts by hand with overrides. From the skill's `scripts/`
   folder, pipe one JSON object to stdin; extra state keys are optional overrides:
   ```bash
   echo '{{"currentState": {{"lc_path": "<path>", "run_tag": "w1", "flatten_window_days": 1.0, "pass1_sigma_upper": 5}}, "assets": {{}}}}' | python prepare.py
   echo '{{"currentState": {{"clean_lc_path": "<from prepare>", "period_min": 0, "period_max": 0, "bls_objective": "snr"}}, "assets": {{}}}}' | python search.py
   ```
   Give each variant its own `run_tag` so its files are kept (they land in
   `<work_dir>/<run_tag>/`). Prewhitening stays automatic when you change the window;
   set `prewhiten` explicitly only to force it on or off. search.py takes the
   `clean_lc_path` of the variant; keep that variant's `prefl_lc_path` and
   `prep_summary` with it.
   Overrides worth trying, one change at a time:
   - Never accept a period that matches `prep_summary.variability.dominant_period_days`
     or a harmonic of it: that is the star, not a planet.
   - Less aggressive flattening (longer `flatten_window_days`, still shorter than the
     rotation period in `prep_summary.variability`), or `prewhiten`: `on`/`off`.
   - Less aggressive outlier removal (`pass1_sigma_upper` 5, `pass2_sigma_upper` 7).
   - The other flag convention (`quality_convention`: `flag0_bad`, `ignore`) when the
     flag diagnostics are ambiguous.
   - A wider or task-specified period range (`period_min`, `period_max`).
   - BLS `bls_objective`: `snr` for correlated noise.
3. Pick the run with a consistent period and the highest broad-search SDE whose
   transit is not an artifact (gap edges, a single event, odd-even mismatch). If
   nothing reaches SDE 6, keep the strongest transit-shaped candidate and say so.
4. Decide the adopted multiple: `as_found`, `double` (odd/even mismatch or alternate
   events missing), or `half` (comparable dip at phase 0.5).

Return JSON for the refinement step, carrying the files from the run you chose:
```json
{{"candidate_period": <float, days>, "period_choice": "as_found|double|half",
 "clean_lc_path": "<path>", "prefl_lc_path": "<path>", "prep_summary": {{<prepare.py output of that run>}},
 "search_summary": {{<search.py output of that run>}},
 "investigation_notes": "<what you tried and why you chose this candidate>"}}
```
