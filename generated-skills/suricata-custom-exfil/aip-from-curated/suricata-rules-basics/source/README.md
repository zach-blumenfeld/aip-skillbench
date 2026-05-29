# Source notes — suricata-rules-basics → AIP

## Origin

`source/SKILL.md` is the verbatim curated Agent Skill from
`vendor/skillsbench/tasks/suricata-custom-exfil/environment/skills/suricata-rules-basics/`.
Used as the canonical source of truth for translating to AIP.

## Schema choice

Schema: `procedure.schema.json` (procedure / runbook family). The
curated skill is fundamentally a multi-step procedure — read
requirements, pick sticky buffers, compose conditions, assemble, verify
— so the procedure schema fits without contortion. No new schema
needed.

## Script-vs-prose decisions

Prose steps (judgment, interpretation):
- `parse-task-requirements` — reading the task brief is interpretive.
- `select-buffers` — mapping the brief's terms onto sticky buffers
  requires judgment (e.g. "this constraint is on a header, not the
  URI").
- `compose-conditions` — picking fragments from
  `references/focused-examples.md` and adapting them.
- `assemble-rule` — laying out the rule in the scaffold.
- `fix-lint-findings` — repairing findings is interpretive.

Script step:
- `lint-rule` (`scripts/lint_rule.py`) — the common failure modes from
  the curated skill ("forgot `http_client_body;`", "`content:"POST"`
  without `http.method;`", "`sig=` without 64-hex pcre", "`blob=`
  without length constraint", missing `sid:`/`rev:`) are deterministic
  pattern checks over rule text. Scripting them once means every
  candidate rule is checked uniformly instead of relying on the agent
  to remember each gotcha.

Lint is heuristic — it cannot prove the rule meets the task's stated
constraints. Step 6 keeps the agent in the loop for that.

## Content mapping

Every section of the source SKILL.md is captured:

- Rule anatomy → step `parse-task-requirements` + scaffold in
  `references/focused-examples.md`.
- Content matching, PCRE, sticky buffers → `select-buffers` +
  `compose-conditions` + `references/focused-examples.md`.
- "Practical tips" (start strict, avoid generic rules, keep msg
  specific) → embedded in step descriptions and `anti_patterns`.
- "Task template: Custom telemetry exfil" scaffold →
  `references/focused-examples.md` (kept intentionally as a scaffold,
  not a working rule — preserves the curated skill's "compose, don't
  copy/paste" stance).
- Focused examples → `references/focused-examples.md` verbatim with
  light reformatting.
- Common failure modes → `references/failure-modes.md` plus
  `anti_patterns` in SKILL.md plus the lint script.

No content was dropped.
