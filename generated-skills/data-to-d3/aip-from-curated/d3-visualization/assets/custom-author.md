Write the D3 page planned in `chart_plan` to the paths in `page_manifest`. D3 is already vendored at `page_manifest.d3_path` (source: {d3_vendor_source}; if that starts with "error", fix the version/path in page_manifest and vendor it by running `scripts/vendor_d3.py` with the state on stdin before continuing).

Task request (verbatim):
{task_request}

Plan: {chart_plan}
Manifest: {page_manifest}
Data profile: {data_profile}

Rules (load `references/d3-rules.md` for the full list, project layout, and tooltip/click/table patterns; load the matching `references/examples/*.js` when you build a bubble/force layout, a linked table, or a tooltip system):
- Put a comment block at the top of the main JS file listing every default you chose.
- Sort rows deterministically before binding (by x, then category); build category domains with explicit sorting.
- No Math.random, no d3-random, no transitions unless asked, fixed width/height/viewBox, explicit d3.format / d3.utcFormat formats, numbers rounded to 2-4 decimals in attributes, stable ids (e.g. "clip-plot").
- Force layouts: deterministic initial positions, `simulation.stop()`, exactly N `tick()` calls, then render.
- If the page must open from file:// (the task says "open it in a browser" or gives no server), embed the data in the JS; d3.csv/fetch is blocked on file://. Copy the raw data too when the task asks.
- Give every mark a `data-key` (or the `key_attr` you chose) so the verifier can find it.
- UTF-8, LF line endings.

Return `page_manifest` (update `expect` if the page differs from the plan).
