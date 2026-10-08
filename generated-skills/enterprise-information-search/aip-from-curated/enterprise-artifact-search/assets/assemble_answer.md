Assemble the final, evidence-backed answer for this enterprise-artifact question.

Question: {question}
Question kind: {question_kind}
Target product: {target_product}  (aliases / codenames: {aliases})

The state holds the evidence gathered so far: `report_candidates`, `selected_report`,
`author_ids`, `reviewer_evidence`, `suggested_reviewer_ids` (document questions) and/or
`conversations`, `url_messages`, `url_registry`, `document_hits`, `meeting_hits`,
`pr_hits`, `cross_product_sweep` (search questions). If `validation_errors` is present,
a previous attempt failed validation: fix every listed error.

Rules that apply to every question:
- Answer only from artifacts proven to belong to the target product. A product's own
  codename (e.g. a planning channel `planning-<Codename>`, doc ids `<codename>_...`,
  meetings `<Codename>_planning_N`) IS the product — it is in the alias list. A name
  that is not in the alias list and dominates an artifact's text is a different product:
  discard it. `cross_product_sweep` hits are distractors unless they pass two grounding
  signals.
- Never use oracle/label fields (ground_truth, gold answers) even if you notice them.
- Values must be retrieved, not inferred: employee ids `eid_…` exactly as in the data
  (resolve a display name to an id only within the product's people — meeting
  participants, channel posters — and only after the artifact is product-grounded),
  URLs copied verbatim.
- De-duplicate, preserving order.
- PRs: only `internal` PRs (github.com/salesforce/<Product or codename>) belong to the
  product. Each workspace also carries upstream open-source PRs (apache/kafka,
  moodle/moodle, …) authored by `EMP_*` ids — those are not employees; ignore them.
  Reviewers of a PR are its `reviews[].user`; approvers are reviews with state APPROVED.

document_people (authors / key reviewers of a named document):
- Report: the `selected_report` (latest > final > newest date > most referenced) of the
  candidates that passed the 2-signal grounding gate. If `valid_report_families` holds
  more than one family with different authors (status AMBIGUOUS), compare their
  `content_head` and signals: prefer the family whose content names the product or the
  codename used in its planning channels and that was shared/reviewed there; if they
  stay equally grounded, keep the selected one, list the others in `notes`, and set
  recommendation AMBIGUOUS.
- Authors: document `author`/`authors`/`created_by`/`owner` fields; else the PR author;
  else the person who posted "Here is the report…" linking that doc id.
- Key reviewers are evidence-based contributors, never just attendees:
  Tier 1 explicit `reviewers`/`key_reviewers`/`approvers`/`requested_reviewers` fields;
  Tier 2 people whose review-meeting turns give concrete suggestions/edits, or who are
  credited for feedback in the document; Tier 3 people replying in the Slack thread under
  the report-share message with substantive feedback, suggestions or questions.
  The review covers every version of the report (draft → final → latest): count
  reviewers of any version. Start from `suggested_reviewer_ids` (Tier 1, then 2, then 3)
  and confirm each against its turns/replies; drop anyone whose only contribution is an
  acknowledgement ("thanks", "looks good", "sounds perfect") unless no other reviewers
  exist. A `participants` entry with no speaking turn is NOT a reviewer. Exclude the
  author from reviewers.
- `unlinked_doc_type_threads` mention the document type but never link a version of the
  selected report. A "Market Research Report on <Competitor>'s product" discussion is a
  distractor. A brainstorm of an "upcoming" report in one of the product's own (alias)
  channels is same-product but pre-draft: nobody in it reviewed a version, and it is not
  authorship unless the selected report's author is in it. Keep both out of the
  author/reviewer lists and name them in `notes`.
- "I agree with X. Also, …" followed by a suggestion of the speaker's own is
  substantive; plain agreement with nothing added is not.
- Fill `report_doc_id`, `author_employee_ids`, `key_reviewer_employee_ids`, and
  `all_employee_ids_union` (authors first); `answer` = the union.

topic_contributors (who provided insights / discussed a topic):
- Read each matching conversation whole. Include people who state substantive content
  on the topic — e.g. for competitor strengths/weaknesses, whoever describes a
  competitor's features, advantages, limitations, risks or drawbacks (usually the
  thread starter, plus any replier who adds an assessment of their own). Exclude people
  who only ask questions, react, or thank. Cover every competitor/topic thread in every
  product channel (planning, planning-…-PM, develop-…, bug-…) and meeting, not just the
  first one found.

shared_links (URLs shared by team members):
- Use `url_messages` (message text + sharer) and confirm the URL in `url_registry`.
  Scope to what the question asks: competitor demos are external links that name a
  competitor product; the product's own demos (`sf-internal.slack.com/archives/<Product>/demo_N`,
  "our product demo") are not competitor demos, and generic articles/blogs are not demos.

Set `recommendation`: USE_EVIDENCE when evidence is sufficient and product-grounded;
NEED_MORE_SEARCH when a required signal is still missing; AMBIGUOUS when product signals
conflict or several equally valid reports remain. Give one evidence record per answer
value with the artifact id exactly as it appears in the data.

Produce `final_answer` as one JSON object in this shape:
{assets[answer_format]}
