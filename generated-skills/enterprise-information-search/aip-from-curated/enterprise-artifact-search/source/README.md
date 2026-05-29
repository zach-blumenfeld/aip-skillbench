# Conversion notes — enterprise-artifact-search (curated → AIP)

## Source
- `ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md` shipped with
  the `enterprise-information-search` task.

## Schema choice
- `procedure.schema.json` (AIP procedure-style Instructions).
  This skill is a multi-step, script-backed retrieval + extraction
  procedure with explicit dependencies between steps, fan-out points
  (parallel candidate searches), and mutually exclusive recommendation
  outcomes — exactly what the procedure schema models. No new schema
  needed.

## Script vs. prose decisions
All scripts live under `scripts/`. We scripted the deterministic mechanics
and left the judgment-heavy decisions as prose for the agent.

- **Scripted (deterministic):**
  - `inspect_product.py` — summarise a product file without dumping it.
  - `find_documents.py` — case-insensitive type/title substring filter
    over `documents`. Reveals whether explicit `reviewers`, `feedback`,
    `approvers`, etc. fields are populated.
  - `select_version.py` — version precedence (`latest` > `final` > most
    recent date > first). Pure precedence, no judgment.
  - `slack_replies_to_doc.py` — locate the share message for a doc link
    plus its `ThreadReplies` AND inline channel follow-ups within a
    time window. The dataset uses inline follow-ups, not threaded
    replies, so a naive `ThreadReplies` walk misses every reviewer
    signal.
  - `parse_transcript.py` — split a meeting transcript into per-speaker
    turns and map names → eids via the position-aligned `participants`
    array. Confirmed empirically that the Attendees header order matches
    the participants list 1:1.
  - `search_slack_text.py` — keyword search across slack with optional
    channel filter; extracts `<url|label>` and bare URLs so q3-style
    "demo URLs shared by team members" questions are one call.
  - `resolve_employee_ids.py` — pattern check, directory presence check,
    and name → eid mapping with explicit ambiguity surfacing.
  - `assemble_output.py` — final dedup (authors first, reviewers next),
    union computation, and eid-pattern validation.

- **Prose (judgment):**
  - Product grounding (which 2+ signals fire for a candidate).
  - Distractor rejection (cross-product leakage when artifact names
    a different product than the file it lives in).
  - Reviewer substantivity (transcript turn or slack reply: real
    feedback vs. "looks good" acknowledgement).
  - Recommendation type (USE_EVIDENCE / NEED_MORE_SEARCH / AMBIGUOUS).

  These hinge on interpreting the artifact contents, not on
  fixed if/then rules over typed fields — exactly the case where a
  prose step beats a script.

## Notes on the dataset (verified against the task fixture)
- Each `products/<Brand>.json` may carry an internal codename in document
  IDs and channel names (e.g., `CoachForce.json` documents use
  `cofoaix_*`; the channel is `planning-CoFoAIX`). The artifact-container
  signal (Signal A in the procedure) is therefore the strongest grounding
  signal — it ties brand → codename. The "report mentions another product
  → distractor" rule from the curated skill applies to artifacts pulled
  from a *different* product file (e.g., `onforcex_*` from
  `ActionGenie.json`), not to the codename inside the correct file.
- Slack thread replies are universally empty in this fixture; replies
  are modelled as subsequent channel messages. `slack_replies_to_doc.py`
  captures both and labels which messages came from the share author.
- Meeting transcripts list attendees by name in a header line; the
  `participants` array is in the same order. Speakers not in the
  attendees list (typically the meeting host / report author) get a
  `null` eid from the script — the agent maps them via the employee
  directory.

## What was deliberately dropped
- The marketing/value-pitch prose ("context savings: 70–95%") — those
  are framing for a human reader and don't change agent behaviour.
- The original Task() invocation example — the agent already knows how
  to invoke a subagent; the skill's body conveys *what* the subagent
  must do.

## Where every source section landed
| Source section | AIP body location |
|---|---|
| When to Invoke | `trigger_when` |
| Why Use | `purpose` (condensed) |
| Step 0 Parse intent | step `parse-intent` |
| Step 1 Build candidate set | step `build-candidate-set` (script-backed) |
| Step 2 Product grounding gate | step `product-ground-and-filter` |
| Step 3 Select version | step `select-version` (script) |
| Step 4 Extract authors | step `extract-authors` (script + judgment) |
| Step 5 Extract reviewers | step `extract-reviewers` (multi-source script + judgment) |
| Step 6 Validate / dedup | step `resolve-and-validate-ids` (script) |
| Output format | step `assemble-output` (script) |
| Recommendation types | step `assemble-output` `one_of` field |
| Common failure modes | `anti_patterns` |
| Mini example | `scenarios` |
| Do NOT invoke when | `do_not_use_when` |
