# xlsx — AIP authoring notes

## Intent

Convert the Anthropic-curated `xlsx` Agent Skill (originally a freeform-markdown
SKILL.md) into an AIP-compliant Procedure skill so an autonomous agent can use
it to create, edit, and analyze `.xlsx` workbooks deterministically — including
formula-bearing financial models where zero formula errors and color/format
conventions are part of the deliverable contract.

The skill's downstream context here is protein-expression analysis (the parent
task family), but the skill itself is general-purpose and identical in scope to
the original. Nothing in the source materials is protein-specific.

## Schema choice

Reused the canonical [procedure](./procedure.schema.json) schema.

Why procedure: the source SKILL.md is a multi-step workflow (choose library →
create/load → modify → save → recalc → verify) with branching on whether
formulas are present, a script-backed recalculation node, and a fixed set of
conventions to enforce when the deliverable is a financial model. That maps
cleanly onto the procedure schema's `steps`, `script`-backed nodes, and
ancillary fields (`anti_patterns`, `scenarios`, `search_shortcuts`).

No new schema needed. No skill-specific fields needed beyond what procedure
already exposes.

## Script vs. prose decisions

**Scripted:**
- `scripts/recalc.py` — copied verbatim from the source. Mandatory after any
  workbook write that includes formulas; deterministic (LibreOffice headless
  recalc + JSON error report). Exactly the kind of node AIP wants in code.

**Prose (not scripted) — and why:**
- Library choice (pandas vs openpyxl). Hinges on what the agent is doing
  (bulk analysis vs formula/formatting work). Data-dependent judgment, not a
  fixed lookup. Prose step.
- Color-coding / number-format conventions for financial models. These are
  fixed *rules*, but applying them requires the agent to classify each cell
  (hardcoded input vs formula vs cross-sheet link vs external link vs key
  assumption) — that classification is the judgment, and there is no
  structured input the agent could feed to a script to do it for them.
  Prose step with the rule table inline.
- Formula verification checklist (range correctness, division-by-zero, cross-
  sheet refs). Reasoning over the model the agent just built, not a
  mechanical pass. Prose.
- "Use Excel formulas, not Python-hardcoded values." A rule with worked
  examples; enforcement is on the agent's code-generation behavior, not on a
  pipeline step. Prose with examples carried into the body.

The split follows the SKILL.md guidance: script the deterministic mechanical
parts (recalc, error scan), leave the judgment-laden parts (classification,
review) as prose the agent reasons through.

## File mapping

| Source file | Destination | Treatment |
|---|---|---|
| `SKILL.md` | `source/ORIGINAL_SKILL.md` + new AIP `SKILL.md` at root | Re-authored into the procedure-schema YAML body. Original kept under `source/` for traceability. |
| `recalc.py` | `scripts/recalc.py` | Copied verbatim. |
| `LICENSE.txt` | `LICENSE.txt` | Copied verbatim. Frontmatter `license` field references it. |

## Name preservation

Skill name is `xlsx` — unchanged from the source. The task harness mounts the
skill at this exact name; renaming would break activation.

## Coverage classification

Walk of the source SKILL.md → AIP body:

- **Mapped** — Requirements for Outputs (zero-error contract, template
  preservation), color-coding standards, number-formatting standards, formula
  construction rules, hardcoded-value documentation pattern, library choice,
  create/edit examples, formulas-not-hardcodes rule, recalc workflow, recalc
  error JSON shape, formula verification checklist, library best practices,
  code-style guidelines — all carried into the body.
- **Deliberate drops** — none. The body preserves every distinct rule and
  example from the source.
- **Schema gaps** — none surfaced.
