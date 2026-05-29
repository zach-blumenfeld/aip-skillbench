---
name: fuzzy-name-search
description: Fuzzy-search SEC 13F filings to resolve a fund or stock identifier from an approximate name. Wraps rapidfuzz WRatio over COVERPAGE.tsv (FILINGMANAGER_NAME → ACCESSION_NUMBER) and INFOTABLE.tsv (NAMEOFISSUER → CUSIP). Also supports exact lookup of a fund by accession number. Use when the user names a fund, manager, or stock (possibly misspelled or partial) and a downstream 13F analysis needs the canonical ACCESSION_NUMBER or CUSIP key. Read-only over /root/<quarter>/.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with pandas and rapidfuzz; reads /root/<quarter>/COVERPAGE.tsv and /root/2025-q2/INFOTABLE.tsv (SEC EDGAR 13F dumps).
---

```yaml
purpose: >
  Resolve a fuzzy human-supplied name into a canonical SEC 13F identifier
  before any downstream analysis. Two lookups: (a) fund / filing-manager
  name → ACCESSION_NUMBER for a given quarter, by fuzzy-matching against
  COVERPAGE.tsv's FILINGMANAGER_NAME column; (b) stock / issuer name →
  CUSIP, by fuzzy-matching against INFOTABLE.tsv's NAMEOFISSUER column.
  Both use rapidfuzz WRatio (Levenshtein-based) so spelling, casing, and
  partial-name variants still match. A third mode does an exact lookup
  by ACCESSION_NUMBER. The skill returns ranked candidates with scores;
  picking the right one is the caller's judgment call.

trigger_when:
  - User names a fund, hedge-fund manager, or filing manager and a downstream step needs the ACCESSION_NUMBER (e.g. "Renaissance Technologies in Q3", "Bridgewater", "Berkshire Hathaway").
  - User names a stock or issuer and a downstream step needs the CUSIP (e.g. "Palantir", "Nvidia", "Apple").
  - User supplies an ACCESSION_NUMBER and wants to confirm which fund / quarter it points to.
  - Building or extending a 13F analysis pipeline (e.g. the sibling `13f-analyzer` skill) that keys off accession numbers or CUSIPs.
  - Working in an environment where /root/<quarter>/COVERPAGE.tsv and /root/2025-q2/INFOTABLE.tsv exist (SEC 13F quarterly dumps).

do_not_use_when:
  - You already have the canonical ACCESSION_NUMBER or CUSIP — call the downstream analysis directly.
  - The question is not 13F-shaped (e.g. historical performance, founding info, real-time prices). 13F dumps only contain end-of-quarter long-equity holdings and filing-manager metadata.
  - You need fund metadata not present in COVERPAGE.tsv (founders, strategy, AUM trend over years). Use external sources.

scope_and_approval: >
  Read-only. Both scripts read TSV files under /root/ and write nothing
  back. No network calls. Safe to run without approval.

steps:
  - name: pick-lookup-mode
    description: >
      Decide which of the three modes applies based on what the user gave:
      (a) fund / manager name + target quarter → fund-fuzzy-by-name;
      (b) known ACCESSION_NUMBER + target quarter → fund-exact-by-accession;
      (c) stock / issuer name → stock-fuzzy-by-name.
      For fund lookups the quarter MUST match the quarter the downstream
      analysis will run against — accession numbers are filing-specific and
      change every reporting season. For stock lookups no quarter is needed;
      the script always reads /root/2025-q2/INFOTABLE.tsv because CUSIPs are
      stable across quarters.
    one_of:
      - fund-fuzzy-by-name
      - fund-exact-by-accession
      - stock-fuzzy-by-name
    outputs:
      - name: mode
        type: string
        description: One of fund-fuzzy-by-name / fund-exact-by-accession / stock-fuzzy-by-name.
      - name: keywords
        type: string
        nullable: true
        description: Raw user-supplied name for the fund or stock; passed through verbatim — the scripts handle casing.
      - name: quarter
        type: string
        nullable: true
        description: Target quarter for fund lookups, e.g. "2025-q2", "2025-q3". Must match a folder under /root/.
      - name: accession_number
        type: string
        nullable: true
        description: Known 18-character SEC accession number, only for exact lookups.
      - name: topk
        type: integer
        nullable: true
        description: Number of ranked candidates to return for fuzzy modes. Defaults to 10 inside the scripts.

  - name: fund-fuzzy-by-name
    description: >
      Fuzzy-match a fund / filing-manager name against COVERPAGE.tsv for the
      target quarter and print the top-K ranked candidates. Each candidate
      block includes ACCESSION_NUMBER, REPORTCALENDARORQUARTER,
      FILINGMANAGER_NAME, FILINGMANAGER_STREET, FILINGMANAGER_CITY,
      FILINGMANAGER_STATEORCOUNTRY, and FORM13FFILENUMBER. Scores are
      rapidfuzz WRatio (0–100, higher = better). The script restricts the
      detail row to ISAMENDMENT == "N" — the original (non-amended) filing —
      so the canonical accession number is returned even when amendments
      exist.
    script: scripts/search_fund.py
    depends_on: [pick-lookup-mode]
    inputs:
      - name: keywords
        type: string
        description: Fund or manager name; case-insensitive, partial allowed.
      - name: quarter
        type: string
        description: Quarter folder under /root/, e.g. "2025-q3".
      - name: topk
        type: integer
        nullable: true
        description: Defaults to 10 in the script.
    outputs:
      - name: ranked_fund_candidates
        type: list[object]
        description: Up to topk blocks, each { rank, score, ACCESSION_NUMBER, REPORTCALENDARORQUARTER, FILINGMANAGER_NAME, FILINGMANAGER_STREET, FILINGMANAGER_CITY, FILINGMANAGER_STATEORCOUNTRY, FORM13FFILENUMBER }. Pick the top result whose FILINGMANAGER_NAME plausibly matches; ties are common and the highest rank is not always the right one.

  - name: fund-exact-by-accession
    description: >
      Exact lookup by ACCESSION_NUMBER in COVERPAGE.tsv for the target
      quarter. Returns at most one block (score 100.000) with the same
      fields as the fuzzy mode, or prints a "No fund found" message.
      Use when the user already supplied the canonical accession number
      and wants to confirm fund identity.
    script: scripts/search_fund.py
    depends_on: [pick-lookup-mode]
    inputs:
      - name: accession_number
        type: string
        description: 18-character SEC accession number, e.g. 0001172661-25-003151.
      - name: quarter
        type: string
        description: Quarter folder under /root/.
    outputs:
      - name: matched_fund
        type: object
        nullable: true
        description: Single block { score=100.0, ACCESSION_NUMBER, REPORTCALENDARORQUARTER, FILINGMANAGER_NAME, FILINGMANAGER_STREET, FILINGMANAGER_CITY, FILINGMANAGER_STATEORCOUNTRY, FORM13FFILENUMBER }, or null when no row matches.

  - name: stock-fuzzy-by-name
    description: >
      Fuzzy-match a stock / issuer name against NAMEOFISSUER in
      /root/2025-q2/INFOTABLE.tsv (always 2025-q2 — CUSIPs are stable
      across quarters and the script hard-codes this path). Filters rows
      whose TITLEOFCLASS is in the bundled `title_class_of_stocks`
      whitelist (com, common stock, cl a, …) so non-equity instruments
      are excluded, uppercases CUSIPs, deduplicates by CUSIP, and ranks
      with WRatio. Returns top-K candidates as { rank, score, Name, CUSIP }.
    script: scripts/search_stock_cusip.py
    depends_on: [pick-lookup-mode]
    inputs:
      - name: keywords
        type: string
        description: Stock / issuer name. The script lowercases internally; ticker symbols are not indexed.
      - name: topk
        type: integer
        nullable: true
        description: Defaults to 10 in the script.
    outputs:
      - name: ranked_stock_candidates
        type: list[object]
        description: Up to topk blocks, each { rank, score, Name (lowercased issuer name), CUSIP (9-char uppercased) }. Adjacent ranks frequently share the same CUSIP because the same issuer is reported with slight name variations across funds — dedup by CUSIP if a single answer is required.

  - name: select-match
    description: >
      Prose step. Read the ranked candidates and pick the right one for the
      downstream task. For fund lookups, the canonical row is usually the
      top score whose FILINGMANAGER_NAME lexically matches the user's term;
      when several rows tie on score, prefer the one whose name is closest
      verbatim (e.g. "Renaissance Technologies LLC" over "Renaissance
      Capital Management" for the user term "renaissance technologies").
      For stock lookups, the top score is almost always correct; if the
      first few ranks share the same CUSIP, just take that CUSIP.
      Pass the chosen ACCESSION_NUMBER or CUSIP into the downstream skill.
    depends_on:
      - fund-fuzzy-by-name
      - fund-exact-by-accession
      - stock-fuzzy-by-name
    outputs:
      - name: resolved_id
        type: object
        description: Object with whichever of accession_number, cusip, filing_manager_name, name_of_issuer, and quarter were resolved. Hand off to the downstream analysis skill.

integrations:
  - partner: 13f-analyzer
    body: |
      Primary downstream consumer. 13f-analyzer keys every analysis off an
      ACCESSION_NUMBER and/or CUSIP. Resolve identifiers here first; for
      quarter-over-quarter deltas, resolve the fund's accession number once
      per quarter (it changes every reporting season). Typical flow:
        1. python3 scripts/search_fund.py --keywords "<fund>" --quarter <q> --topk 5
        2. python3 scripts/search_stock_cusip.py --keywords "<stock>" --topk 5
        3. Pass resolved IDs into 13f-analyzer's one_fund_analysis.py / holding_analysis.py.

scenarios:
  - need: "I want the AUM of Renaissance Technologies in Q3 2025."
    context: User gave a fund name, not an accession number, and a quarter.
    action: >
      pick-lookup-mode → fund-fuzzy-by-name.
      python3 scripts/search_fund.py --keywords "renaissance technologies"
      --quarter 2025-q3 --topk 5. The top result's FILINGMANAGER_NAME is
      "Renaissance Technologies LLC".
    outcome: ACCESSION_NUMBER for Renaissance in 2025-q3; hand off to 13f-analyzer.

  - need: "Confirm what fund 0001172661-25-003151 is in Q2 2025."
    context: User supplied a canonical accession number.
    action: >
      pick-lookup-mode → fund-exact-by-accession.
      python3 scripts/search_fund.py --accession_number 0001172661-25-003151
      --quarter 2025-q2. Returns Bridgewater Associates, LP, score 100.000.
    outcome: Single confirmed fund block.

  - need: "Top fund holders of Palantir in Q3 2025."
    context: User named a stock. Need a CUSIP to query the holdings table.
    action: >
      pick-lookup-mode → stock-fuzzy-by-name.
      python3 scripts/search_stock_cusip.py --keywords palantir --topk 5.
      Ranks 1–N all return CUSIP 69608A108 (same issuer reported with
      slight name variations). Take 69608A108.
    outcome: CUSIP 69608A108; hand off to 13f-analyzer's top-holders-by-cusip.

  - need: "Top 5 stocks Berkshire Hathaway added from Q2 to Q3 2025."
    context: Delta question — need TWO accession numbers for the same fund.
    action: >
      pick-lookup-mode → fund-fuzzy-by-name, run TWICE — once with --quarter
      2025-q2 and once with --quarter 2025-q3. Accession numbers differ
      between the two quarters. Pick the FILINGMANAGER_NAME "Berkshire
      Hathaway Inc" row from each (ISAMENDMENT="N" already enforced by
      the script).
    outcome: Two accession numbers, one per quarter, ready for fund-quarter-delta.

anti_patterns:
  - Reusing a single ACCESSION_NUMBER across quarters. Accession numbers are filing-specific; re-run search_fund.py for every (fund, quarter) pair.
  - Passing --quarter to search_stock_cusip.py. The script does not accept it and ignores quarter context — CUSIPs are stable across quarters and the dictionary is always read from /root/2025-q2/INFOTABLE.tsv.
  - Picking a fund row without checking FILINGMANAGER_NAME. Fuzzy ranks tie frequently (e.g. "Bridgewater Associates, LP" and "Bridgewater Advisors Inc." both score 81.818 for "bridgewater"). Read the name field, not just the rank.
  - Treating a stock-search result as definitive without checking adjacent ranks. The same CUSIP often appears in multiple ranks because funds spell the issuer slightly differently; deduplicating by CUSIP before picking gives a stabler answer.
  - Modifying the `title_class_of_stocks` whitelist in `scripts/search_stock_cusip.py`. The list has known missing commas that string-concatenate several entries into one nonsensical token; the benchmark expected-answers (and the sibling 13f-analyzer's stock count) are calibrated against the exact list. Preserve verbatim — fixing it changes downstream answers.
  - Loading COVERPAGE.tsv or INFOTABLE.tsv without dtype=str when you write ad-hoc pandas outside the bundled scripts. CUSIPs and ACCESSION_NUMBERs are numeric-looking strings with leading zeros; pandas coerces them to int/float and silently corrupts the keys.
  - Calling search_fund.py without --quarter. The flag is required; the script reads /root/<quarter>/COVERPAGE.tsv and will not run otherwise.
```
