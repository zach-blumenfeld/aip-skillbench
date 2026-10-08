# Enterprise artifact dataset — format notes

Root (in the task container): `/root/DATA` (the scripts also accept its parent).

- `metadata/employee.json` — `{eid: {employee_id, name, role, location, org}}`.
  ~530 people; display names repeat across orgs (e.g. eleven "David Davis"), so a name
  alone never identifies a person. Resolve names inside the product's people first
  (meeting `participants`, channel posters, `@eid_` mentions).
- `metadata/salesforce_team.json` — org tree (VP → leads → engineers, PMs, architects,
  UX researchers, marketing). Roles only; no product assignment.
- `metadata/customers_data.json` — external customer contacts (`CUST-*` ids), not employees.
- `products/<Product>.json` — one workspace per product:
  - `slack[]`: `{Channel{name, channelID}, Message{User{userId, timestamp, text,
    utterranceID}, Reactions}, ThreadReplies[], id}`. `ThreadReplies` is normally empty:
    a conversation is the run of messages in one channel whose `id` shares the
    `YYYYMMDD` prefix (`YYYYMMDD-<seq>-<hash>`), ordered by `<seq>`. Unrelated chatter
    (PR reviews, `@here` article links) can interleave in the same channel-day.
    `slack_admin_bot` messages are join/create notices.
  - Channels: `planning-<Codename>`, `planning-<Product>`, `planning-<Product>-PM`,
    `planning-<LongName>`, `develop-<person>-<Product>`, `bug-<person>-<Product>`.
  - `documents[]`: `{id, type, author, date, document_link, content, feedback?}`. Types:
    Market Research Report, Product Vision Document, Product Requirements Document,
    Technical Specifications Document, System Design Document. Versions share a stem:
    `<stem>` (draft) → `final_<stem>` → `latest_<stem>`. `feedback` lists the edits
    requested for that version, unattributed.
  - `meeting_transcripts[]`: `{id, date, document_type, participants[eid], transcript}`;
    transcript text is `Attendees\n<names>\nTranscript\n<Name>: <utterance>…`. The
    presenter (usually the author) speaks but may be absent from `participants`.
    `<Codename>_planning_N` meetings review one document type each;
    `product_dev_<Name>_N` are all-hands with ~50 participants.
  - `meeting_chats[]`: `{id: <meeting_id>_chat, text}` — usually the doc link shared.
  - `urls[]`: `{id, link, description}` — every URL posted in the workspace.
  - `prs[]`: `{id, title, summary, link, state, merged, user{login}, reviews[{user{login},
    state, comment, submitted_at}]}`. Only `github.com/salesforce/<Product|Codename>/pull/N`
    PRs are the product's; the rest are upstream open-source PRs (kafka, moodle, kibana…)
    with `EMP_*` logins that are not in the employee directory.

## Codenames

Each product was planned under a codename before it got its product name: CoachForce's
workspace is full of `CoFoAIX` (`planning-CoFoAIX`, `cofoaix_market_research_report`,
`CoFoAIX_planning_1`), PersonalizeForce's of `onalizeAIX` and "Einstein Adaptive
Personalization". Those are the same product. `locate_product.py` derives this alias
list from the workspace itself; treat any name outside it as a different product.
