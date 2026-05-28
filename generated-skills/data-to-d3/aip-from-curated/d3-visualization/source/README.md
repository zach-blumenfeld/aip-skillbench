# Source notes — d3-visualization AIP conversion

## Provenance

- **Curated SKILL.md:** `CURATED_SKILL.md` — verbatim copy of the curated `SKILL.md` shipped in `tasks/data-to-d3/environment/skills/d3-visualization/`.
- **Schema used:** `procedure.schema.json` — the AIP `Procedure` schema (v0.3a2). The curated source describes a graph-shaped procedure (inputs → render → outputs, with non-negotiable determinism gates), so `Procedure` is the natural fit; no new schema was authored.
- **Companion JS patterns** (preserved at the skill root under `references/`):
  - `bubble_chart_example.js` — clustered bubble chart w/ force layout
  - `tooltip_handler.js` — reusable conditional-tooltip class
  - `interactive_table_example.js` — sortable / two-way-highlight table
  - `check_tooltip.js` — in-browser sanity check for tooltip wiring

  These are pattern catalogs the agent reads, not procedure-step backings, so they live under `references/` per AIP best practice (scripts/ is for code the procedure calls).

## Name / folder mismatch (deliberate)

The curated frontmatter declares `name: d3js-visualization` while the parent folder is `d3-visualization`. The host task mounts the skill by folder name and expects the curated `name:` value to be preserved verbatim. The AIP `name<->folder` rule is therefore intentionally relaxed here — the validator will report a `name_mismatch` error; that error is the *expected* behavior for this conversion. Other AIP guarantees (schema validity, body-against-schema, bundled schema) still hold and are exercised by the validator.

## Completeness check (curated → AIP body)

Walked the curated SKILL.md section by section against the compiled body. Classification:

| Curated section | Classification | Landing in AIP body |
|---|---|---|
| Top-line "what + when" | **Mapped** | `purpose`, `trigger_when` |
| "When to use" bullet list | **Mapped** | `trigger_when` |
| "If only a table/summary, don't use D3" | **Mapped** | `do_not_use_when` |
| Expected inputs (data files, intent fields, constraints) | **Mapped** | `steps.gather-intent.inputs` + that step's description |
| Default-output triad (HTML / SVG / optional PNG) | **Mapped** | `steps.export-outputs` + scenarios |
| Determinism rules — data | **Mapped** | `steps.sort-and-format-data` (description + anti-patterns) |
| Determinism rules — rendering | **Mapped** | `steps.author-d3-render` description + `check_determinism.py` rules + anti-patterns |
| Determinism rules — offline/dependency | **Mapped** | `steps.vendor-d3` + anti-patterns + `check_determinism.py` `no-cdn-d3` rule |
| Determinism rules — file (stable IDs, LF, rounded numerics) | **Mapped** | `steps.author-d3-render` description + anti-patterns |
| Recommended project layout (`dist/`, `vendor/`) | **Mapped** | `steps.vendor-d3`, `steps.export-outputs` |
| Tooltip pattern (HTML / CSS / JS) | **Mapped** (by reference) | `steps.add-interactivity-if-needed` → `references/tooltip_handler.js` and inline tooltip section |
| Click handlers for selection | **Mapped** (by reference) | same step → `references/interactive_table_example.js` |
| Conditional interactivity | **Mapped** | same step (description + anti-patterns: "always-show tooltip") |
| Determinism-as-non-negotiable framing | **Mapped** | `scope_and_approval` + `steps.validate-determinism` (validation loop) |
| All four JS example files | **Mapped** | preserved verbatim under `references/`; referenced in matching steps |

No deliberate drops. Pinned D3 version (7.9.0), default-output folder (`dist/`), and the LF/rounding rules are all carried over into the body or the determinism validator.

## Why a `check_determinism.py`?

The curated source flags determinism rules as "non-negotiable" and enumerates fixed lookups (no `Math.random`, no CDN `<script src=...>`, no `d3.random*`, no `Date.now()`, fixed `viewBox`). That is precisely the "fixed set of rules" case that the AIP best-practice guide says **must** be backed by a script. `scripts/check_determinism.py` implements those rules as one-line regex/string lookups and is invoked from the `validate-determinism` step. The step also runs twice (once on draft, once on final) to enforce the validation-loop pattern from the AIP skill-creation guide.
