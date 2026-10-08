# Source and provenance

`enterprise-artifact-search/SKILL.md` (copied verbatim) is the curated Agent Skill
"Enterprise Artifact Search Skill (Robust)". It's the only source. It describes one
workflow: multi-hop retrieval and structured extraction over an enterprise artifact
dataset, with product grounding and evidence-based reviewer rules. It was compiled into
the AIP procedure in `../SKILL.md`.

I also read the dataset the skill runs on (`/root/DATA`: 30 `products/<Product>.json`
workspaces plus `metadata/employee.json`, `salesforce_team.json`,
`customers_data.json`; the files were full size, not truncated) to learn the real
format. Scripts and gotchas come from that inspection. Nothing in the pack hardcodes an
answer. Every value is computed from whatever dataset `data_root` points to.

## Graph and step-kind choices

| Step | Kind | Why |
|---|---|---|
| `locate-product` | execution | Matching product file names / codenames in the question, deriving aliases from the workspace, mapping the document type through a synonym table (`assets/doc_types.json`), and building an inventory are deterministic lookups. |
| `classify-question` | decision (choice) | Which evidence path a question needs is a judgment over a fixed label set (document_people / topic_contributors / shared_links / other). A router branches on it. |
| `route-kind` | router | Named-document questions go to the dedicated report extractor. Everything else goes to the keyword sweep. |
| `report-evidence` | execution | Source Steps 1–6 are mostly rules: collect candidates, score grounding signals A–E, apply the ≥2-signal gate and the distractor reject, pick the version (latest > final > date > references), read author fields, read reviewer fields, find the share message and its conversation, parse transcripts, and resolve speaker names to eids. All of these are scriptable. |
| `plan-search` | client_task | Choosing search terms (and the next hop's entity names) is generation that depends on the question and the previous sweep. |
| `search-artifacts` | execution | Keyword sweep over every artifact type, conversation grouping, URL extraction, PR filtering, entity hints, and the cross-product sweep (source Step 1 "global sweep"). Deterministic. |
| `evidence-check` | decision (noul) | Source recommendation NEED_MORE_SEARCH as a gate: is the evidence complete, or does another hop remain? A low threshold (0.2) because stopping early is the costly error. |
| `route-evidence` | router | Loops back to `plan-search` until the evidence is sufficient (agent caps it at round 3). |
| `assemble-answer` | client_task | Telling substantive feedback from acknowledgement, deciding who "provided insights", scoping links (competitor vs own-product demos), and writing the evidence map all need reading and judgment. The scripts pre-sort (`substantive` flags, `suggested_reviewer_ids`, `internal` / `about_own_product` flags), but the agent decides. |
| `validate-answer` | execution | Source Step 6 (valid `eid_` ids that exist in the directory, de-dup in order, authors first) plus checks that URLs and artifact ids exist in the data. Fixed rules. |
| `route-validation` | router | A failed validation goes back to `assemble-answer` with `validation_errors` in the state. |

Scripts are stdlib-only Python (the task container installs only `python3`). They
share `scripts/eas_lib.py`.

## Source → body map (completeness check)

| Source item | Where it lives |
|---|---|
| Purpose: multi-hop retrieval + structured extraction, lean context, JSON-ready entities + evidence pointers | `purpose`, `description`, `assets/answer_format.json` |
| When to invoke (5 conditions) | `trigger_when` (all five, merged with the dataset's question shapes) |
| Do NOT invoke when (2 conditions) | `do_not_use_when` |
| Invocation via `Task(subagent_type=…)` with the dataset root, the question verbatim, and output requirements | Start inputs `question` (verbatim) and `data_root`. Output requirements are in the `assemble-answer` template and answer format. See the drop log for the subagent mechanism. |
| Constraints: avoid oracle/label fields; prefer primary artifacts over metadata shortcuts; MUST enforce product grounding | `assemble_answer.md` rules; `anti_patterns` (last item); grounding gate in `report_evidence.py` |
| Step 0: parse target product, entity types, artifact types; infer cautiously or mark AMBIGUOUS | `locate-product` (product, codename, doc type), `classify-question` (entity / path); `target_product` input description (empty → search everything, AMBIGUOUS unless the artifacts settle it) |
| Step 1: search order: product file → global sweep → follow doc links / meeting chats / PR mentions; candidate criteria (type/title, doc links or Slack text, meeting `document_type`) | `report_evidence.py` (doc type match, share messages via `/archives/docs/<id>`, meetings by `document_type`, meeting chats, PR mentions, `unlinked_doc_type_threads` for Slack text that only mentions the type); `search_artifacts.py` (`cross_product_sweep`, all-workspace scope when there's no product) |
| Step 2: grounding signals A–E, valid if ≥2 | `report_evidence.py` `signals` / `signal_count` / `valid` |
| Step 2 reject rule: content repeatedly names a different product without target grounding → DISTRACTOR | `report_evidence.py` `distractor` (another product's alias outnumbers the target's and the content never names the target); `assemble_answer.md` first rule; `anti_patterns` |
| Step 2 why: benchmarks plant the same doc type across products; first hit wins is a failure | `anti_patterns` ("Taking the first report hit") |
| Step 3: version precedence latest > final > date > most referenced; keep doc_id + link as anchor | `report_evidence.py` `rank()` / `selected_report`; `assemble_answer.md` |
| Step 4: authors from `author/authors/created_by/owner` → PR author → Slack "Here is the report…" poster, only if linked and grounded; normalize to eid; resolve names only after grounding | `report_evidence.py` (`AUTHOR_FIELDS`, fallback to share posters); `assemble_answer.md` (author order, PR author, name resolution after grounding) |
| Step 5 Tier 1 / 2 / 3 reviewer rules, exclusions (author, pure acknowledgements unless nothing else), participants ≠ reviewers, cite transcript lines | `report_evidence.py` (`explicit_fields`, `meetings[].speakers` with turns, `silent_participants`, `slack_threads[].replies` with `substantive`, `suggested_reviewer_ids` in tier order); `assemble_answer.md` document_people rules; `anti_patterns` |
| Step 6: valid `eid_` ids that exist in the directory; de-dup preserving order, authors first then reviewers | `validate_answer.py` |
| Output: final answer object (target_product, report_doc_id, author ids, key reviewer ids, union) | `assets/answer_format.json` (`report_doc_id`, `author_employee_ids`, `key_reviewer_employee_ids`, `all_employee_ids_union`, plus a generic `answer`) |
| Output: evidence map per id (artifact type + id + snippet) | `answer_format.json` `evidence[]`; `validate_answer.py` requires one record per value and checks that the artifact ids exist |
| Recommendation types USE_EVIDENCE / NEED_MORE_SEARCH / AMBIGUOUS | `answer_format.json` `recommendation`; `report_status` from `report_evidence.py`; the `evidence-check` loop carries NEED_MORE_SEARCH |
| Failure modes 1–4 (cross-product leakage, over-inclusive reviewers, wrong version, schema mismatch) | `anti_patterns` items 2, 4, 3, 8 |
| Mini example (CoachForce MRR) | Became the functional test. The CoFoAIX claim was corrected (see below). |

## Corrections to the source (checked against the data)

- **CoFoAIX is not a distractor.** The source's example says to reject reports about
  "CoFoAIX" when asked about CoachForce. In the dataset, `products/CoachForce.json` is
  written almost entirely under that codename: channel `planning-CoFoAIX`, docs
  `cofoaix_*`, meetings `CoFoAIX_planning_N`, PR repo `salesforce/CoFoAIX`. Every
  product has such a codename (PersonalizeForce → onalizeAIX / Einstein Adaptive
  Personalization). Following the source literally rejects every real report. The
  pack keeps the source's mechanism ("a canonical alias list you derive from
  artifacts"): `derive_aliases` builds the list from planning channel names,
  meeting-series ids, and doc-id prefixes of docs that were actually shared in the
  workspace's Slack. The reject rule then applies to names outside that list.
- **The real distractors** are a "Market Research Report on Gong.io's product" thread
  in the same planning channel, brainstorms of an "upcoming" report in a second
  planning channel, unshared or other-family report docs (`*prox_*_final`, `new_*`),
  and upstream open-source PRs with `EMP_*` logins. Each one is surfaced and flagged
  (`unlinked_doc_type_threads`, `valid_report_families` + AMBIGUOUS, PR `internal`).

## Additions from the data (not in the source)

- Slack `ThreadReplies` is empty. A conversation is the channel-day id prefix, so the
  "thread replies to the report-share message" are the following messages in that
  group.
- Display names repeat across orgs (92 duplicated names). Transcript speakers are
  resolved inside the meeting's participants and the author first, then the product
  roster. Ambiguous names are reported, never guessed.
- Topic and link questions (the dataset's other question shapes: competitor insights,
  demo URLs) get a search loop. The source only details the report case but claims
  coverage of "docs/chats/meetings/PRs/URLs".

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| Delegation to a subagent (`Task(subagent_type="enterprise-artifact-search", …)`) and the "typical context savings 70–95%" claim | Mechanism and marketing, not procedure. In AIP the scripts keep large files out of context (they return compact evidence), which serves the same goal. The prompt's content (question verbatim, dataset root, output requirements, constraints) is carried by the start inputs and the templates. |
| "Why use this skill? Without/with" narrative | Rationale. Its actionable parts (follow cross-links, verify product scope, compact evidence map) are steps. |
| "This version adds two critical upgrades" preamble | Changelog. Both upgrades (grounding, reviewer rules) are encoded. |
| Literal "reject CoFoAIX when asked about CoachForce" example | Contradicted by the data (see Corrections). The rule it illustrates is kept. |
