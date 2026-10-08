Plan the next keyword sweep for this enterprise-artifact question.

Question: {question}
Question kind: {question_kind}
Target product: {target_product}
Product aliases / codenames: {aliases}
Document type named in the question (may be empty): {doc_type}

Produce `search_terms`: a list of 3–10 literal strings that search-artifacts will match
case-insensitively against Slack messages, documents, meeting transcripts, PRs and the
URL registry of the target product's workspace (every workspace if no product is known).

How to pick terms:
- Use the words the artifacts themselves would use, not the question's phrasing. Slack
  people write "competitor", "weakness", "strength", "drawback", "demo", "take a look at",
  "Market Research Report", "PR", product or competitor names.
- Round 1: the topic words from the question plus close synonyms (e.g. competitor
  questions: "competitor", "weakness", "strength", "drawback", "demo").
- Later rounds (the state already holds `conversations`, `entity_hints`, `url_messages`
  from the previous sweep): hop on what you learned. Add the specific names found
  (competitor products, features, document ids, people) so the sweep catches messages
  that never repeat the generic word — e.g. a demo link that names the competitor but
  never says "competitor". Drop terms that only produced noise.
- Do not add "http", "https" or ".com" as terms: every link in the workspace matches and
  the real hits drown. Search for the words around a link ("demo", a competitor name).
- Do not add the product name itself as a term; every message in the workspace is
  already about the product, so it only adds noise.
- Set `search_round` to 1 on the first sweep and increment it on each loop. Stop looping
  after round 3: answer with what you have and mark it NEED_MORE_SEARCH if gaps remain.
