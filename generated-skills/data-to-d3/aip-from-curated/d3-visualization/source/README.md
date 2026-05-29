# Source notes — `d3js-visualization`

## Origin
Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/data-to-d3/environment/skills/d3-visualization/SKILL.md`.
The original `SKILL.md` is preserved verbatim in this folder as `SKILL.md`.

## Why the procedure schema
The source is a workflow: take local data → set up a deterministic D3
project → load/sort → design encodings → render HTML/SVG → optionally add
interactivity → export → verify. That is exactly the shape
`procedure.schema.json` is designed for (an ordered, input/output-connected
execution graph with optional interactivity). No new schema needed.

## Script vs prose decisions
The source skill is judgement-heavy. The interesting decisions —
"infer chart type", "design scales", "what counts as deterministic enough"
— hinge on interpreting loosely-specified input. AIP guidance says: script
the deterministic/mechanical parts, leave interpretive parts as prose. So:

- **Prose steps (no `script:`):** every step. None of the procedure's
  decision points reduces to a fixed lookup table, numeric threshold, or
  if/then over structured input. They are all "look at the task and the
  data, decide what to render."
- **`scripts/` directory:** carries the four JS files from the source
  verbatim. These are *reference implementations* (tooltip class, bubble
  chart, interactive table, tooltip runtime check) the agent reads and
  adapts when wiring its output — not scripts the AIP runtime invokes as
  procedure nodes. They are kept under `scripts/` (rather than
  `references/` or `assets/`) to match the original skill's layout, since
  the curated skill explicitly stores them there and the body refers to
  them by that path.

## Content classification
Every distinct piece of the source `SKILL.md` is captured in the new body:

| Source content | Where it lands |
| --- | --- |
| Top-line purpose ("turn data into reproducible D3 visualizations") | `purpose` |
| "When to use" bullet list | `trigger_when` |
| "Don't use D3 for quick tables/summaries" | `do_not_use_when` |
| Inputs to expect (data files, intent, constraints) | `gather-intent` step |
| "Make reasonable defaults and document them in comments" | `scope_and_approval` + `gather-intent` |
| Outputs (`dist/chart.html`, `chart.svg`, optional `chart.png`) | `prepare-layout-and-vendor-d3`, `render-chart`, `export-svg` |
| Data determinism rules (sort, stable group order, locale formatting) | `load-and-sort-data`, `design-scales-and-encodings`, `anti_patterns` |
| Rendering determinism (no random, no transitions, fixed dims, force-layout caveats) | `render-chart`, `anti_patterns` |
| Offline/dependency determinism (no CDN, pin D3, vendor) | `prepare-layout-and-vendor-d3`, `anti_patterns` |
| File determinism (stable IDs, LF, numeric precision) | `render-chart`, `export-svg`, `anti_patterns` |
| Recommended project layout (`dist/`, `vendor/`) | `prepare-layout-and-vendor-d3` |
| Interactive features — tooltip pattern, click handlers, conditional interactivity, key points | `add-interactivity` step + `references/interactivity.md` |
| Worked code (bubble chart, table, tooltip handler, tooltip check) | `scripts/*.js`, referenced from `add-interactivity` |

No content from the source was deliberately dropped.

## Known frontmatter quirk
The output folder name is `d3-visualization` (per the user's mount-path
constraint) but the `name:` field is `d3js-visualization` (the harness
requires this exact name on the mounted skill). Per the AIP spec the folder
name normally equals `name`; that rule is intentionally relaxed here. The
validator may flag the mismatch — the directive from the user takes
precedence.
