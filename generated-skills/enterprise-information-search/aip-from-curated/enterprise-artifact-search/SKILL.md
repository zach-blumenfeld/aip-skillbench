---
name: enterprise-artifact-search
description: Multi-hop evidence search + structured extraction over enterprise artifact datasets (docs/chats/meetings/PRs/URLs). Strong product disambiguation to prevent cross-product leakage; explicit reviewer-evidence rules to prevent "meeting participants == reviewers" mistakes; returns JSON-ready entities plus evidence pointers.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Retrieve and extract structured entities (employee IDs, document IDs,
  URLs) from enterprise artifact datasets where a workspace contains many
  interlinked artifacts — documents, slack channels, meeting transcripts,
  PRs, and URLs — plus reference metadata (employee/customer directories).
  Optimised for multi-hop questions where the answer must be retrieved
  from artifacts (not inferred), where evidence is scattered across
  artifact types, and where the dataset contains intentional cross-product
  distractors. Returns a strict JSON answer object plus an evidence map of
  artifact pointers and supporting snippets, so the host agent can verify
  every output.

trigger_when:
  - The question requires multi-hop evidence gathering (artifact → references → other artifacts).
  - The answer must be retrieved from artifacts (IDs, names, dates, roles), not inferred.
  - Evidence is scattered across multiple artifact types (docs + slack + meetings + PRs + URLs).
  - The host agent needs precise pointers (doc_id, message_id, meeting_id, pr_id) to justify outputs.
  - The host agent must keep its context lean and avoid loading large product files.
  - The dataset places same-typed artifacts (e.g., a "Market Research Report") across multiple products and one product must be disambiguated from the rest.

do_not_use_when:
  - The answer is in a single small known file with no cross-references.
  - The task is a trivial one-hop lookup and product scope is unambiguous.

scope_and_approval: >
  Read-only. The skill reads files under the dataset root (default
  `/root/DATA`) and runs the bundled scripts under `scripts/`. It does
  not modify any artifact, write to the dataset, or call external
  services. The host agent is responsible for any downstream action.

steps:
  - name: parse-intent
    description: >
      Extract from the question: (a) target product name (e.g.,
      "CoachForce"), (b) entity types required (author employee IDs,
      key reviewer employee IDs, URLs, etc.), (c) artifact types
      likely relevant (e.g., "Market Research Report", "Product
      Vision Document"). If the product name is missing, infer
      cautiously from nearby context only when explicitly supported
      by artifacts; otherwise mark target_product as AMBIGUOUS and
      surface that in the recommendation.
    outputs:
      - name: intent
        type: object
        description: "{target_product, entity_types, artifact_types, ambiguous: bool}"

  - name: inspect-product-file
    description: >
      Load a compact summary of the target product's artifact file
      (channels, document headers, meeting transcript headers, URLs,
      PR headers) without dumping the full file into context. Default
      path is `<dataset_root>/products/<TargetProduct>.json`. If the
      file is not present under that exact name, scan the
      `products/` directory and pick the file whose channels or
      document IDs name the target product or a clear codename
      (e.g., `planning-<TargetProduct>`).
    depends_on: [parse-intent]
    script: scripts/inspect_product.py
    inputs:
      - name: intent
        type: object
    outputs:
      - name: product_summary
        type: object
        description: "channels, documents, meeting_transcripts, urls, prs (headers only)"

  - name: build-candidate-set
    description: >
      Build the candidate artifact set with wide recall. Sources to
      consult, in order:
        1. Documents whose `type` (or `title`) contains the required
           artifact type substring (script: find_documents.py).
        2. Meeting transcripts whose `document_type` equals or
           contains the required artifact type.
        3. PRs whose title/summary mention the artifact type.
        4. Slack messages whose text references the artifact type or
           a doc link of that type (script: search_slack_text.py).
      For the q1-style "Market Research Report" pattern, calling
      `find_documents.py` with the type substring is sufficient as
      the primary anchor.
    depends_on: [inspect-product-file]
    parallel: true
    script: scripts/find_documents.py
    inputs:
      - name: product_summary
        type: object
      - name: intent
        type: object
    outputs:
      - name: candidates
        type: list[object]

  - name: product-ground-and-filter
    description: >
      Apply the HARD product grounding gate. A candidate is VALID only if it
      passes at least 2 independent grounding signals from the list below.
      Reject candidates that pass < 2 as DISTRACTORS even when they appear
      first in search results.

      Grounding signals (pick any 2+):
        A. Located inside the correct product's artifact container
           (e.g., the file resolved in inspect-product-file) AND
           associated with that file's planning channels or meetings.
        B. Document content or title explicitly names the target
           product OR a canonical alias/codename derived from the
           artifact file (e.g., the planning channel name).
        C. Shared in a channel whose name clearly belongs to the
           target product (`planning-<Product>`, `planning-<Codename>`,
           `#<product>-*`) OR a product-specific meeting series
           (`<Product>_planning_*`, `<Codename>_planning_*`).
        D. The document id or link path contains a product-specific
           identifier consistent with the target product / codename
           (not another product's codename).
        E. A meeting transcript discussing the candidate references
           the target product in its title, series, or channel.

      Reject rule: if a candidate is pulled from a DIFFERENT
      product's artifact file (e.g., a `onforcex_*` doc when
      target is CoachForce / CoFoAIX), reject as DISTRACTOR even if
      the artifact type matches. Same-codename artifacts inside the
      correct product file are NOT distractors — they are the
      canonical artifacts under that brand's internal codename.

      The "report mentions another product" check from the curated
      rule applies cross-file, not within-file: a CoFoAIX-named
      report inside `CoachForce.json` is the CoachForce artifact;
      a CoFoAIX-named report inside `ActionGenie.json` is the
      distractor.
    depends_on: [build-candidate-set]
    inputs:
      - name: candidates
        type: list[object]
      - name: product_summary
        type: object
    outputs:
      - name: grounded_candidates
        type: list[object]
      - name: rejected_distractors
        type: list[object]

  - name: select-version
    description: >
      If multiple grounded candidates exist, pick the canonical
      version using a fixed precedence: explicit `latest` marker in
      id/link/title > explicit `final` marker > most recent date >
      first in input order. The selected artifact's id and link
      become the anchor for author/reviewer extraction.
    depends_on: [product-ground-and-filter]
    script: scripts/select_version.py
    inputs:
      - name: grounded_candidates
        type: list[object]
    outputs:
      - name: anchor_artifact
        type: object

  - name: extract-authors
    description: >
      Extract authors from the anchor artifact in priority order:
        1. Document fields: `author`, `authors`, `created_by`, `owner`.
        2. If the artifact was introduced via a PR, the PR
           `user.login` / `created_by` of that PR.
        3. The slack user who posted "Here is the report …" — only
           when the message clearly links to the anchor's
           `document_link` AND is product-grounded by signal C.
      Treat the result as a list of identifier strings (eids or
      names). Pass the list to resolve-and-validate-ids for
      normalisation.
    depends_on: [select-version]
    inputs:
      - name: anchor_artifact
        type: object
    outputs:
      - name: author_candidates
        type: list[string]

  - name: extract-reviewers
    description: >
      Extract key reviewers as evidence-based contributors. DO NOT
      equate meeting `participants` with reviewers — participants
      alone is NEVER sufficient.

      Tier 1 — explicit reviewer fields. Document `reviewers`,
      `key_reviewers`, `approvers`, `requested_reviewers`; PR
      `reviewers`, `requested_reviewers`, `reviews[].user.login`. If
      Tier 1 yields signal, prefer it.

      Tier 2 — explicit feedback authors. Use `parse_transcript.py`
      on every transcript whose `document_type` matches the anchor's
      type AND that is product-grounded. From the parsed turns, keep
      speakers whose turns carry concrete feedback (suggestions,
      edits, specific section critiques, questions seeking change).
      Exclude the meeting host / report author and pure
      acknowledgements. The script's `name_to_eid` mapping (built
      from the position-aligned `participants` array) resolves names
      to eids. The agent decides substantivity — the script does
      not.

      Tier 3 — slack follow-ups on the share message. Use
      `slack_replies_to_doc.py` with the anchor's doc id (or its
      core slug) and a 6–24h follow-up window. Keep users who
      reply with concrete feedback. Exclude the share author
      (unless the question explicitly wants them) and pure
      "looks good" / "thanks" acks unless no Tier 1/2 signal exists.

      If document `feedback` text is populated but author
      attributions are missing, use it as corroboration for Tier 2/3
      candidates — not as a standalone source.
    depends_on: [select-version]
    parallel: true
    inputs:
      - name: anchor_artifact
        type: object
      - name: product_summary
        type: object
    outputs:
      - name: reviewer_candidates
        type: list[string]
      - name: reviewer_evidence
        type: list[object]
        description: "per candidate: artifact_type, artifact_id, supporting snippet"

  - name: resolve-and-validate-ids
    description: >
      Normalise every author and reviewer identifier into a
      canonical employee ID. Calls `resolve_employee_ids.py` with
      the employee directory (default
      `<dataset_root>/metadata/employee.json`). Items already
      matching `eid_*` and present in the directory are kept;
      bare names are resolved by case-insensitive directory lookup;
      ambiguous names (multiple matches) are surfaced as
      unresolved. The agent must resolve ambiguity by cross-
      referencing meeting `participants`, channel members, or
      explicit eids in adjacent slack messages before adding to
      the final list.
    depends_on: [extract-authors, extract-reviewers]
    script: scripts/resolve_employee_ids.py
    inputs:
      - name: author_candidates
        type: list[string]
      - name: reviewer_candidates
        type: list[string]
    outputs:
      - name: validated_authors
        type: list[string]
      - name: validated_reviewers
        type: list[string]
      - name: unresolved
        type: list[object]

  - name: assemble-output
    description: >
      Build the final JSON answer object and the evidence map.
      Order-preserving dedup: authors first, then reviewers (a
      reviewer who is also an author is kept under authors only).
      Compute `all_employee_ids_union`. Validate every emitted id
      against the `eid_*` pattern; surface malformed entries in
      `_warnings`. Pick a recommendation: USE_EVIDENCE when both
      authors and reviewers are populated and grounded;
      NEED_MORE_SEARCH when reviewer signal is missing despite a
      grounded anchor; AMBIGUOUS when product grounding conflicts
      or multiple equally valid anchors remain after select-version.
    depends_on: [resolve-and-validate-ids]
    script: scripts/assemble_output.py
    inputs:
      - name: anchor_artifact
        type: object
      - name: validated_authors
        type: list[string]
      - name: validated_reviewers
        type: list[string]
      - name: reviewer_evidence
        type: list[object]
    outputs:
      - name: final_answer
        type: object
      - name: evidence_map
        type: list[object]
      - name: recommendation
        type: string
    one_of:
      - USE_EVIDENCE
      - NEED_MORE_SEARCH
      - AMBIGUOUS

modes:
  - name: default
    body: >
      Run as a fresh subagent against a single dataset root.
      Sequence: parse-intent → inspect-product-file →
      build-candidate-set → product-ground-and-filter →
      select-version → (extract-authors ‖ extract-reviewers) →
      resolve-and-validate-ids → assemble-output. Return the
      final answer JSON + evidence map only.
  - name: url-extraction
    body: >
      For questions about URLs shared by team members (e.g., demo
      URLs for competitor products), skip select-version and the
      author/reviewer extraction tiers. Instead, after
      product-ground-and-filter, call `search_slack_text.py` with
      the topical keywords (e.g., `["demo", "competitor", <competitor-name>]`)
      and a channel filter naming the product's planning channel(s).
      Aggregate `urls_in_text` plus the URL artifacts from
      `product_summary.urls` that match the keyword set, dedupe, and
      return alongside the slack message ids as evidence.
  - name: insight-extraction
    body: >
      For questions about who provided insights on a topic (e.g.,
      competitor strengths/weaknesses), drive extract-reviewers
      with topic-specific keywords against
      `search_slack_text.py` and `parse_transcript.py` instead of
      anchoring on a specific document. Substantivity check still
      applies — keep speakers/posters who described concrete
      strengths or weaknesses, not those who only acknowledged.

integrations:
  - partner: Host agent (main loop)
    body: >
      Invoke this skill as a subagent with the dataset root and the
      verbatim question. The host agent receives a compact JSON
      answer + evidence map; it should not need to re-read product
      files. Typical context savings: 70–95% versus inline search.
  - partner: Employee directory (DATA/metadata/employee.json)
    body: >
      Required for name → eid resolution and eid validation.
      `resolve_employee_ids.py` accepts either dict-keyed-by-eid or
      list-of-records shapes and surfaces ambiguity explicitly.

scenarios:
  - need: >
      "Find employee IDs of the authors and key reviewers of the
      Market Research Report for the CoachForce product."
    context: >
      `products/CoachForce.json` exists; documents inside use the
      internal codename `cofoaix_*`; planning channel is
      `planning-CoFoAIX`. Three Market Research Report versions:
      `cofoaix_market_research_report`,
      `final_cofoaix_market_research_report`,
      `latest_cofoaix_market_research_report`.
    action: >
      inspect-product-file on CoachForce.json; find_documents
      yields 3 grounded candidates (all in the correct file);
      select-version picks `latest_cofoaix_market_research_report`;
      author from doc `author` field; reviewers from the slack
      follow-ups in `planning-CoFoAIX` on the share message and
      from the transcript turns in `CoFoAIX_planning_1`, filtering
      out acknowledgements and the report author.
    outcome: >
      USE_EVIDENCE with author + reviewer eids, anchored on
      `latest_cofoaix_market_research_report`. Reject any
      `onforcex_*` / `onalizeaix_*` Market Research Report from
      other product files as DISTRACTOR even though they share
      the type.

  - need: >
      "Find the demo URLs shared by team members for
      PersonalizeForce's competitor products."
    context: >
      `products/PersonalizeForce.json`. Competitor products are
      named in slack discussion threads in the planning channels
      (`planning-PersonalizeForce`, `planning-PersonalizeForce-PM`)
      and in the Product Vision / Market Research Report's
      Competitive Analysis section.
    action: >
      url-extraction mode: identify competitor names by reading the
      anchor's Competitive Analysis section + scanning planning
      channels for "competitor" / "demo" keywords; call
      `search_slack_text.py` with those competitor names plus
      `["demo"]`; collect `urls_in_text`; cross-check against
      `product_summary.urls` for matching descriptions.
    outcome: >
      A list of (demo_url, sharing_user_id, slack_message_id)
      triples plus the supporting URL descriptions.

anti_patterns:
  - First-hit-wins on artifact type — picking a Market Research Report from another product's file just because it appeared earlier in the search results.
  - Treating meeting `participants` as the key reviewers list. Reviewers must contribute substantive feedback in a transcript turn, an explicit reviewer field, or a slack reply.
  - Choosing a draft over the `latest` / `final` version of an artifact when the version markers are present in the id or link path.
  - Returning a flat list of employee IDs when the output schema requires split `author_employee_ids` and `key_reviewer_employee_ids`.
  - Walking `ThreadReplies` only — in this dataset replies are inline channel follow-ups, so a thread-only walk silently returns zero reviewers.
  - Rejecting a same-file artifact that names the product's internal codename (e.g., dismissing `cofoaix_market_research_report` from `CoachForce.json` as "wrong product").
  - Loading whole product JSON files into the host agent's context instead of summarising via `inspect_product.py` first.
  - Resolving an ambiguous name (multiple eids) without cross-referencing channel membership, meeting participants, or adjacent slack eids.
```
