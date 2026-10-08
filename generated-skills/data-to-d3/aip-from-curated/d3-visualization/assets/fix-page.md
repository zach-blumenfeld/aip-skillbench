The verifier rejected the page. Fix the generated files so every failure goes away, then hand back the manifest for re-verification.

Verification result:
{verification}

Manifest: {page_manifest}

Task request (verbatim):
{task_request}

- Fix each failure at its cause in the generated HTML/JS/CSS (or regenerate: for the bubble page you may correct `viz_spec` and re-run `scripts/build_bubble_page.py` with the state on stdin). Load `references/d3-rules.md` for the rules and patterns.
- Typical causes: a remote/CDN script (vendor D3 locally with `scripts/vendor_d3.py`); d3 loaded after the script that uses it; Math.random or an un-stopped force simulation (non-identical SVG across loads); overlapping or out-of-bounds bubbles (smaller `radius_range`, larger `height`, or more ticks); tooltip hidden by `display:none` or missing `pointer-events:none`; labels intercepting the mouse (`pointer-events:none` on text); data loaded with d3.csv failing on file:// (embed it).
- Only change `page_manifest.expect` when the expectation itself was wrong for this task (e.g. a different mark count the task requires), never to hide a real defect.
- Warnings are advisory; act on them when the task cares (e.g. it opens the page from file://).

Return `page_manifest`.
