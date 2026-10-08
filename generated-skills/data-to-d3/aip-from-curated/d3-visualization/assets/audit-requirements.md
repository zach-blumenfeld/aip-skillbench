Audit the generated page against the task, requirement by requirement, and close every gap before verification.

Task request (verbatim):
{task_request}

Page manifest (files written, expectations the verifier will test):
{page_manifest}

Build/vendor notes: {build_report}

1. Split the task request into atomic requirements: every output path, every visual encoding (size, color, clustering, labels, legend), every tooltip field and exclusion, every table column/header/format, every interaction, every library/version/offline constraint, and anything else it asks for.
2. For each one, open the generated file that should satisfy it (HTML, JS, CSS, copied data) and confirm it does. Do not trust the spec; read the output.
3. If something is missing or different, edit the generated files directly to satisfy it, keeping the determinism rules: no Math.random/d3-random, no transitions, fixed width/height/viewBox, sorted domains, local D3 only, LF line endings. Keep `data-key` attributes, `circle.bubble`, `#data-table tbody tr`, `#tooltip` and the `.visible` toggle so the verifier still applies. Load `references/d3-rules.md` for the rules and the interaction patterns.
4. If an edit changes what the verifier should expect (e.g. another mark count, a different selector), update `page_manifest.expect` to match.

Return `requirement_check`: a list of objects `{{"requirement", "status": "met" | "fixed" | "not-applicable", "where"}}` (where = file and what satisfies it), plus `page_manifest` (updated or unchanged).
