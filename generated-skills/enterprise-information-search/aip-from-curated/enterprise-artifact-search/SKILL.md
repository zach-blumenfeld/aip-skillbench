---
name: enterprise-artifact-search
description: Multi-hop evidence search and structured extraction over enterprise artifact datasets (per-product Slack channels, documents, meeting transcripts and chats, PRs, URLs, plus employee directory). Answers questions like "employee IDs of the authors and key reviewers of the Market Research Report for <Product>", "who gave insights on competitor products", "demo URLs shared for competitors" with JSON-ready values and evidence pointers. Enforces product grounding (codenames vs distractor products), final/latest version selection, and evidence-based reviewer rules.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Answer one retrieval question over an enterprise artifact dataset (a products/ folder
  with one JSON workspace per product holding Slack, documents, meeting transcripts and
  chats, PRs and URLs, plus metadata/employee.json) with values copied from the data
  (employee ids, doc ids, URLs) and an evidence pointer for each. Scripts locate the
  product and its codenames, gate candidate reports on two independent product-grounding
  signals, pick the final/latest version, resolve meeting speakers to employee ids, and
  sweep conversations for multi-hop follow-up; the agent judges who actually reviewed or
  contributed and assembles the answer, which a script validates against the dataset.

trigger_when:
  - A question asks for employee ids, document ids, names, dates or URLs that must be retrieved from enterprise artifacts (docs, Slack, meetings, PRs, URLs), not inferred.
  - The question names a product and a document type, e.g. "authors and key reviewers of the Market Research Report for CoachForce".
  - The question asks who discussed or gave insights on a topic (competitors, strengths/weaknesses, features) or which links/demos were shared for a product.
  - Evidence is scattered across artifact types and needs multi-hop follow-up (artifact → link → other artifact) with precise pointers (doc_id, message id, meeting id, pr id).
  - A question file lists several such questions (e.g. /root/question.txt); run the procedure once per question.

do_not_use_when:
  - The answer is in a single small known file and location with no cross-references.
  - The task is a trivial one-hop lookup and product scope is unambiguous.

steps:
  - name: locate-product
    kind: execution
    description: Resolve the dataset root, the target product (file name or workspace codename), its alias list, the named document type, and an artifact inventory.
    inputs:
      - name: question
        type: string
        description: The question, verbatim.
      - name: data_root
        type: string
        description: Dataset root holding products/ and metadata/ (in the task container /root/DATA).
    script: scripts/locate_product.py
    assets:
      - assets/doc_types.json
    inputs_to: classify-question

  - name: classify-question
    kind: decision
    description: Decide which evidence path the question needs.
    inputs:
      - name: question
        type: string
      - name: target_product
        type: string
        description: Product the question is about; empty when none was named (then search every workspace and mark the answer AMBIGUOUS unless artifacts settle it).
      - name: doc_type
        type: string
        description: Document type named in the question, or empty.
    questions:
      question_kind:
        type: choice
        instructions: What does the question ask to be retrieved?
        criteria:
          document_people: The authors, reviewers, owners or contributors of one named document (Market Research Report, Product Vision / Requirements, Technical Specifications, System Design).
          topic_contributors: The people who discussed, explained or gave insights on a topic (competitor products, strengths/weaknesses, a feature, an issue) in chats or meetings.
          shared_links: URLs, links or demos that team members shared.
          other: Anything else retrievable from the artifacts (doc ids, dates, PR facts, counts).
    thresholds:
      question_kind: 0.6
    inputs_to: route-kind

  - name: route-kind
    kind: router
    description: Named-document questions get the report extractor; everything else gets the keyword sweep.
    branch_on: question_kind
    branches:
      document_people: report-evidence
      topic_contributors: plan-search
      shared_links: plan-search
      other: plan-search

  - name: report-evidence
    kind: execution
    description: Collect candidate reports, apply the 2-signal grounding gate and distractor reject, select latest > final > newest > most-referenced, and gather author plus reviewer evidence (fields, meeting turns, Slack thread replies, PRs) with ids resolved.
    inputs:
      - name: data_root
        type: string
      - name: target_product
        type: string
      - name: doc_type
        type: string
      - name: aliases
        type: list[*]
        description: Product name plus codenames from its own workspace.
    script: scripts/report_evidence.py
    inputs_to: evidence-check

  - name: plan-search
    kind: client_task
    description: Choose the literal search terms for the next sweep, hopping on names found in the previous one.
    inputs:
      - name: question
        type: string
      - name: question_kind
        type: string
      - name: target_product
        type: string
      - name: aliases
        type: list[*]
      - name: doc_type
        type: string
    template: assets/plan_search.md
    references:
      - path: references/dataset-format.md
        description: Workspace JSON layout, how Slack conversations group by id prefix, channel naming, document versions, transcript format, codenames. Load when choosing where a fact would live or when results look wrong.
    inputs_to: search-artifacts

  - name: search-artifacts
    kind: execution
    description: Sweep the product workspace for the terms; return whole matching conversations, URL-bearing messages with sharers, URL registry, document / meeting / PR hits, entity hints, and a cross-product sweep.
    inputs:
      - name: data_root
        type: string
      - name: target_product
        type: string
      - name: aliases
        type: list[*]
      - name: search_terms
        type: list[*]
        description: Literal strings to match case-insensitively.
      - name: search_round
        type: integer
        description: 1 on the first sweep, incremented on each loop.
    script: scripts/search_artifacts.py
    inputs_to: evidence-check

  - name: evidence-check
    kind: decision
    description: Decide whether the gathered evidence answers the question or another sweep is needed.
    inputs:
      - name: question
        type: string
      - name: question_kind
        type: string
    questions:
      evidence_sufficient:
        type: noul
        instructions: >
          Does the state already hold product-grounded evidence for every part of the
          question? For document_people: a selected report, its author, and reviewer
          evidence (explicit fields, meeting turns, or Slack replies). For topic and link
          questions: every relevant thread across all the product's channels and meetings,
          including follow-up threads that name the specific entities (e.g. each competitor
          by name, each demo link). If search_round is already 3, answer true and let the
          answer carry NEED_MORE_SEARCH for any gap.
        criteria:
          true: Every requested value has a grounded artifact behind it and no obvious follow-up hop (a named entity not yet searched) remains.
          false: A required signal is missing, report_status is NEED_MORE_SEARCH or AMBIGUOUS, or entity_hints / conversations name entities that were not yet swept.
    thresholds:
      evidence_sufficient: 0.2
    inputs_to: route-evidence

  - name: route-evidence
    kind: router
    description: Sufficient evidence goes to answer assembly; otherwise plan another sweep.
    branch_on: evidence_sufficient
    branches:
      "true": assemble-answer
      "false": plan-search

  - name: assemble-answer
    kind: client_task
    description: Apply the grounding, version, author, reviewer, contributor and link-scope rules to the evidence and write the JSON answer with evidence pointers.
    inputs:
      - name: question
        type: string
      - name: question_kind
        type: string
      - name: target_product
        type: string
      - name: aliases
        type: list[*]
    template: assets/assemble_answer.md
    assets:
      - assets/answer_format.json
    references:
      - path: references/dataset-format.md
        description: Dataset layout, name-to-id resolution caveats (display names repeat across orgs), document version stems, transcript format, codenames. Load when resolving names or checking an artifact id.
    inputs_to: validate-answer

  - name: validate-answer
    kind: execution
    description: Check every id against the employee directory, every URL and evidence artifact id against the data, de-duplicate in order, and rebuild the authors-then-reviewers union.
    inputs:
      - name: data_root
        type: string
      - name: final_answer
        type: object
        description: The answer object in the shape of assets/answer_format.json.
    script: scripts/validate_answer.py
    inputs_to: route-validation

  - name: route-validation
    kind: router
    description: A valid answer ends the run; validation errors go back to assembly.
    branch_on: answer_valid
    branches:
      "true": end
      "false": assemble-answer

  - name: end
    kind: end
    description: The validated answer object with evidence pointers and a recommendation.
    inputs:
      - name: final_answer
        type: object
        description: JSON-ready answer, evidence map, and USE_EVIDENCE / NEED_MORE_SEARCH / AMBIGUOUS.
      - name: answer_valid
        type: boolean

anti_patterns:
  - Treating a product's codename as a distractor. CoachForce's workspace is written as CoFoAIX (planning-CoFoAIX, cofoaix_* doc ids, CoFoAIX_planning_N meetings); names in the derived alias list are the same product. Reject only names outside it.
  - Taking the first report hit. The same document type exists in every product, and a planning channel can discuss a "Market Research Report" on a competitor (e.g. Gong.io); only reports passing two grounding signals count.
  - Picking the draft when final_ or latest_ versions exist.
  - Counting meeting participants as reviewers. Only people with feedback turns, explicit reviewer fields, or substantive replies to the report-share thread count; acknowledgements do not.
  - Resolving a display name to an employee id against the whole directory. Names repeat across orgs; resolve within the meeting participants or product team.
  - Stopping at the first competitor thread. Competitor discussions are spread across planning, planning-…-PM and develop-… channels; sweep again with each competitor's name.
  - Returning the product's own demo links (sf-internal.slack.com/archives/<Product>/demo_N) or generic articles when competitor demos are asked for.
  - Returning a flat list for a document_people question; fill the split author / key reviewer / union fields.
  - Reading oracle fields (ground_truth, gold answers) or metadata-only shortcuts instead of primary artifacts.
```
