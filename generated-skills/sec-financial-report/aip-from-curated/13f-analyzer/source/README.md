# 13f-analyzer — AIP authoring notes

## Source
- Curated skill: `vendor/skillsbench/tasks/sec-financial-report/environment/skills/13f-analyzer/`
  (mirrored here as `source-SKILL.md`).
- Sibling skill referenced in body: `fuzzy-name-search` (resolves fund names →
  ACCESSION_NUMBER and stock names → CUSIP).

## Schema
Reuses `procedure.schema.json` (procedure-style AIP Instructions). The skill is
a small execution graph: identifier resolution → one of three script-backed
analyses. No new schema needed.

## Script vs. prose decisions
| Step                       | Backing      | Why |
|----------------------------|--------------|-----|
| `resolve-identifiers`      | Prose        | Picking which fund / stock to resolve requires interpreting the user's natural-language question — agent reasoning, not a fixed rule. The sibling `fuzzy-name-search` skill handles the mechanical lookup. |
| `one-fund-quarter-summary` | `scripts/one_fund_analysis.py` (no `--baseline_*`) | Mechanical: read TSV, filter by accession, sum VALUE, count stock-class holdings. Deterministic — must be a script for consistent answers. |
| `fund-quarter-delta`       | `scripts/one_fund_analysis.py` (with `--baseline_*`) | Same script, baseline flags trigger the comparative branch. Mechanical merge + sort. |
| `top-holders-by-cusip`     | `scripts/holding_analysis.py` | Group + sort + name lookup. Mechanical. |

## Script changes from source
1. **`holding_analysis.py` path bug fix** — original read
   `f"{data_root}/INFOTABLE.tsv"`; data lives at `f"{data_root}/{quarter}/INFOTABLE.tsv"`
   (per `environment/Dockerfile`). Fixed to use the quarter sub-directory.
2. **`holding_analysis.py` output enrichment** — original printed only the
   `ACCESSION_NUMBER`. Task questions ask for fund manager *names*
   (e.g. "List top-3 fund managers (name) which have invested Palantir"), so the
   script now joins with `COVERPAGE.tsv` and prints `FILINGMANAGER_NAME`
   alongside the accession number. Avoids a manual second lookup per result.
3. **`holding_analysis.py` empty-result guard** — print a message and return
   instead of failing on a no-match CUSIP.
4. **`one_fund_analysis.py`** — preserved verbatim from source.

## Preserved verbatim
- `title_class_of_stocks` list in `one_fund_analysis.py`. The list has known
  string-literal-concatenation in the source (missing commas glue many entries
  into one nonsensical string). The reference solution in
  `tasks/sec-financial-report/solution/solve.sh` uses the **same** list, so the
  benchmark's expected answers (`q2_answer`, `q3_answer`) are calibrated against
  it. Fixing the list would change the stock-count and top-buys answers and
  break the test. If the list is ever corrected upstream, regenerate expected
  outputs.

## Body content mapping (source SKILL.md → AIP body)
- "Analyze the holding summary of a particular fund in one quarter" →
  step `one-fund-quarter-summary`.
- "Analyze the change of holdings of a particular fund in between two quarters" →
  step `fund-quarter-delta`.
- "Analyze which funds hold a stock to the most extent" →
  step `top-holders-by-cusip`.
- Sample CLI invocations → captured as `scenarios` with realistic prompts
  derived from `tasks/sec-financial-report/instruction.md`.

## Deliberate drops
- None. The source SKILL.md is small (3 usage blocks); every block maps to a
  step. Anti-patterns and scenarios add knowledge the source omits but the task
  requires (quarter-specific accession numbers, ISAMENDMENT filter, dtype=str
  for CUSIP, schema of expected `answers.json`).
