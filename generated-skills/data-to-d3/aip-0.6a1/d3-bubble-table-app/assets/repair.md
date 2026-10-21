# Repair the D3 web app until every verification check passes

The app in `{output_dir}` (built from the data in `{data_dir}`) failed verification.

Task statement:

{instruction}

Verification report (the `failures` list names each failed check and what was observed):

{verify_report}

Do this:

1. For each failure, find the cause in `{output_dir}` (`index.html`, `css/style.css`, `js/visualization.js`, `js/d3.v6.min.js`, `data/`). Load `references/app-structure.md` for where each behaviour lives and `references/d3-patterns.md` for the canonical patterns.
2. Fix the cause, not the check. Typical fixes:
   - missing or wrong files, wrong D3 version, incomplete `data/` copy: re-run `python3 scripts/build_app.py --data-dir {data_dir} --output-dir {output_dir}` from the skill folder (it overwrites the app files and recopies the data; re-apply any intentional customizations afterwards).
   - overlap or bubbles outside the SVG: lower the area share in `layout()` or raise the forceCollide iterations; never drop forceCollide.
   - clusters mixed: strengthen forceX/forceY or widen the anchor ring gap.
   - tooltip shown for an ETF / no-market-cap row, or missing ticker/name/sector: fix `showTooltip`.
   - highlight not linked: `selectTicker` must set `selected` on both the bubble and the row whose `data-ticker` matches.
   - side by side broken: `.dashboard` must stay a non-wrapping row flexbox; shrink the table's min-width before the chart.
3. If a failed check contradicts an explicit requirement of the task statement (for example the task asks the table to omit ETFs but the check expects every row), the task wins: keep the task's behaviour, do not undo it to satisfy the check, and list the conflicting check in `repair_summary`. Fix every other failure.
4. Re-run `python3 scripts/verify_app.py --data-dir {data_dir} --output-dir {output_dir}` from the skill folder and repeat until `verify_passed` is true. If a check cannot pass in this environment (e.g. no browser available), say so explicitly instead of claiming success.

Answer with `repair_summary` (what was wrong, what you changed, and any check left failing on purpose because the task overrides it) and `recheck_passed` (true only when every remaining failure is such a task-mandated conflict or the re-run passed outright; false if anything else still fails).
