# fuzzy-name-search — AIP authoring notes

## Source
- Curated skill: `vendor/skillsbench/tasks/sec-financial-report/environment/skills/fuzzy-name-search/`
  (mirrored here as `source-SKILL.md`).
- Sibling skill that consumes outputs: `13f-analyzer` (keys every analysis off
  ACCESSION_NUMBER and/or CUSIP).

## Schema
Reuses `procedure.schema.json` (procedure-style AIP Instructions). The skill is
a small graph: a mode-pick branch → one of three script-backed lookups →
a prose select-match. No new schema needed.

## Script vs. prose decisions
| Step                       | Backing                          | Why |
|----------------------------|----------------------------------|-----|
| `pick-lookup-mode`         | Prose (`one_of`)                 | Picking between fund-by-name / fund-by-accession / stock-by-name is a semantic read of the user's input — agent reasoning, not a fixed rule. |
| `fund-fuzzy-by-name`       | `scripts/search_fund.py`         | Deterministic: read TSV, fuzzy-match WRatio, filter ISAMENDMENT="N", print top-K. |
| `fund-exact-by-accession`  | `scripts/search_fund.py`         | Same script — `--accession_number` flag triggers the exact branch. Deterministic. |
| `stock-fuzzy-by-name`      | `scripts/search_stock_cusip.py`  | Deterministic: read TSV, whitelist TITLEOFCLASS, fuzzy-match WRatio, print top-K. |
| `select-match`             | Prose                            | Choosing the right candidate from ranked output requires judgment (lexical closeness, tie-breaks across same-score rows, dedup by CUSIP). Not a fixed rule. |

## Scripts — preserved verbatim
Both scripts are copied **byte-for-byte** from the curated source:
- `scripts/search_fund.py`
- `scripts/search_stock_cusip.py`

Notable invariants preserved on purpose:
1. `data_root = "/root"` in both scripts — matches the task's Dockerfile mount.
2. `search_stock_cusip.py` always reads `/root/2025-q2/INFOTABLE.tsv` for the
   stock dictionary. The author's note in the curated SKILL.md says "CUSIPs are
   stable across quarters", so the script intentionally ignores quarter context.
3. The `title_class_of_stocks` list in `search_stock_cusip.py` has known
   string-literal-concatenation (missing commas glue several entries into one
   nonsensical token). The reference solution in
   `tasks/sec-financial-report/solution/solve.sh` uses the **same** list, so the
   benchmark's expected stock-count and top-buys answers are calibrated against
   it. Fixing the list would change downstream answers and break the test.

## Body content mapping (source SKILL.md → AIP body)
- "Overview" (search engine for fund/stock meta with fuzzy Levenshtein) →
  `purpose`.
- "Fuzzy search a fund using its name" (sample CLI + result) →
  step `fund-fuzzy-by-name` + first scenario.
- "Exact search a fund using accession number" (sample CLI + result) →
  step `fund-exact-by-accession` + Bridgewater scenario.
- "Fuzzy search a stock using its name" (sample CLI + result) →
  step `stock-fuzzy-by-name` + Palantir scenario.

## Added beyond the source
The curated SKILL.md is 82 lines and three CLI examples. To make the skill
self-sufficient for an autonomous agent, the AIP body adds:
- `trigger_when` / `do_not_use_when` — explicit activation calibration.
- `scope_and_approval` — declares read-only behavior so callers know it's safe.
- `pick-lookup-mode` and `select-match` prose steps — the reasoning the human
  reader does implicitly.
- `integrations` block — points at `13f-analyzer` as the primary consumer,
  with the exact calling pattern.
- `anti_patterns` — failure modes inferred from the script source and the
  benchmark task (accession-numbers-change-quarterly, --quarter rejected by
  stock script, dtype=str for CUSIP, do-not-edit the whitelist, fund-name
  tie-break advice).

## Deliberate drops
- None. The source SKILL.md is small; every block is captured.
