---
name: skill-distillation
description: Create refined skills that gate quality at write time and improve reliability and performance. Use whenever authoring a skill an autonomous agent will consume, including net-new skills, and compiling existing material (runbooks, deliberations, specs, decision logs, post-mortems). Default to using this any time the consumer is an autonomous agent — this skill is what makes a skill production-grade.
---

# Skill Distillation

## Trigger When

1. Authoring an agent skill (SKILL.md) for an autonomous agent
2. Validating an existing distilled skill

## Do not Use When

- Authoring one-off prompts
- Authoring content no agent will consume (human-only wikis, FAQs, casual notes)


## Skill Structure

Use the directory structure of [Agent Skills](https://agentskills.io/specification.md) with the addition of a `source/` directory.

```shell
skill-name/
├── SKILL.md                       # Required: metadata + instructions
├── source/                        # Required: the canonical human-readable material this skill was compiled from
│   ├── README.md                  # Recommended: provenance and the log of what was deliberately dropped, with rationale
│   └── ...                        # Runbooks, specs, decision logs, or other material sourced to create this skill
├── scripts/                       # Optional: executable code
├── assets/                        # Optional: templates, resources
├── references/                    # Optional: documentation
└── ...                            # Any additional files or directories
```
In the `SKILL.md` body, also include the following sections:
 - **Trigger When**: Conditions under which the agent should consider this skill. Mixed granularity expected: immediate invocation triggers alongside broader applicability contexts belong in the same list.
 - **Purpose**: What the skill encapsulates as a coherent unit of work: the scope it covers and what it adds beyond general agent knowledge. One short paragraph.

### Skill Components
In general the skill should be structured into discrete components: `execution` runs a script, `decision` asks typed questions, `client_task` hands work to the agent running the skill. See [Choose Component Kinds](#choose-component-kinds) for when to use each. 

### Optional directories

#### `scripts/`

Contains executable code that agents can run. Scripts should:

* Be self-contained or clearly document dependencies
* Include helpful error messages
* Handle edge cases gracefully

Supported languages depend on the agent implementation. Common options include Python, Bash, and JavaScript.

#### `references/`

Contains additional documentation that agents can read when needed:

* `REFERENCE.md` - Detailed technical reference
* `FORMS.md` - Form templates or structured data formats
* Domain-specific files (`finance.md`, `legal.md`, etc.)

Keep individual reference files focused. Agents load these on demand, so smaller files mean less use of context.

#### `assets/`

Contains static resources:

* Templates (document templates, configuration templates)
* Images (diagrams, examples)
* Data files (lookup tables, schemas)

### Progressive disclosure

Agents load skills in three tiers, pulling more detail only as needed:

1. **Metadata (~100 tokens).** `name` and `description` load at startup for *every* installed skill. `description` is the only signal an agent has before deciding to activate the skill — make it specific and keyword-rich.
2. **Body (target <5000 tokens, ~500 lines).** The full `SKILL.md` body loads once the skill activates.
3. **Resources (on demand).** Files under `scripts/`, `references/`, and `assets/` load only when the skill body references them. Tell the agent *when* to load each (e.g., "Read `references/api-errors.md` if the API returns a non-200 status").

If the body would exceed the budget, push detail into `references/` rather than letting `SKILL.md` bloat. Body tokens cost every invocation; reference tokens cost only when loaded.

### File references

When referencing other files in your skill, use relative paths from the skill root:

```markdown SKILL.md
See [the reference guide](references/REFERENCE.md) for details.

python scripts/extract.py
```

## Best Practices

### Choose Component Kinds
Structure the skill into components and make each one as deterministic as its logic allows: script what can be scripted, ask a typed question where the input must be judged, and leave free-form reasoning only for what genuinely needs it. The three component kinds follow in order of preference. Pick the first that fits, and note the choice and why in `source/README.md`.

1. **Script (`execution`)** when the logic can be written as code over the declared inputs:
   - domain-specific logic
   - **deterministic** if/then/else, when/unless, or "only if" rules over structured inputs
   - lookup tables
   - numeric calculations, thresholds, or caps
   - validation against a fixed set of rules
2. **Decision (`decision`)** when the component must judge the input — which case applies, whether a condition holds, how severe something is — and the answer space can be written down before seeing the input: yes/no, one of a fixed set, or a position on a described scale. The answer is a typed value the rest of the skill can act on: a later step can branch on it, a script can take it as input, or the result can report it. Mark the questions where an uncertain answer must be reconsidered.
3. **Client task (`client_task`)** only when the output must be generated by the agent itself: text, code, a plan, a synthesis. In this case `client` refers to the agent using the skill. If a judgment seems to need information the skill has not yet gathered, add an earlier script that gathers it instead of falling back to a client task.

While scripting is critical, scripting the wrong things results in brittle errors and over-restriction. Leaving to free-form reasoning what a script or decision can do also costs speed, consistency, and calibration.

#### When Writing Scripts
**Be lean and fast — prefer a maintained library over re-implementing a heavy algorithm (e.g. an optimization solver). You don't know the consumer's runtime budget - default to efficient; slow scripts risk timing out.**

Favor fewer script files for simplicity.  Only create separate scripts files for truly independent self-contained logic.

If the skill has scripts, declare what they need in two places. In the frontmatter `compatibility` field, name the interpreter with its minimum version, the packages the scripts import (pip names, optionally `name>=version`), and any other tools they call. Repeat the same in a header comment at the top of each script. In the body, tell the agent to check these before running the first script and to name everything missing. Wherever the body invokes a script, give the exact launch command (`python scripts/extract.py`, or `bash scripts/run.sh` run from the script's folder).

#### When Writing Decisions

There are three types:
1. **Noul** for one yes/no question. Phrase it so a high value means yes; make the boundary unambiguous; add `criteria` with `true` and `false` when the boundary needs spelling out. [Docs](https://docs.typesafe.ai/primitives/noul)
   ```yaml
   has_personal_data:
     type: noul
     instructions: Does the message contain personal data?
     criteria:
       true: Names, emails, phone numbers, addresses, or account identifiers appear.
       false: No identifying details beyond what is needed to answer the sender.
   ```
2. **Choice** for a decision over a fixed set of labels. Descriptions must separate the options from each other; include an `other` option when inputs may fall outside the list. [Docs](https://docs.typesafe.ai/primitives/choice)
   ```yaml
   team:
     type: choice
     instructions: Which team should handle this ticket?
     criteria:
       billing: Charges, invoices, refunds, subscription payments.
       technical: Errors, outages, or a feature not working.
       other: Fits neither.
   ```
3. **Score** for a position on an ordered scale, lowest level first. Describe situations, not degrees; one dimension per question — split a multifaceted judgment into separate scores. [Docs](https://docs.typesafe.ai/primitives/score)
   ```yaml
   severity:
     type: score
     instructions: How severe is the reported bug?
     criteria:
       - Cosmetic; everything still works.
       - A feature is degraded but a workaround exists.
       - A core feature is unusable for the reporter.
   ```
The agent running the skill answers each question by its own judgment and reconsiders any answer that is a close call.

Further advice ([System One concepts](https://docs.typesafe.ai/concepts/system-one)):
- Put every question about the same input in one decision component; the agent answers them all in one pass.
- The decision's input is the content being judged. Criteria go in `instructions` and `criteria`, not in the input.
- Give each question a name and use that name wherever the rest of the skill refers to its answer. Answers are the choice labels, `true`/`false` for a noul, or level numbers for a score.
- For each question, say which kind of mistake is costly: when a false positive is costly, tell the agent to reconsider any close call that leans yes; when a false negative is costly, the reverse.
- If a question only applies to some inputs (severity only matters for bugs), say what the answer is for the others in its `instructions` ("non-bugs are level 0"), or ask it only after an earlier question has established that the input is a bug. Otherwise the agent hedges on every input it does not apply to.


### Use Simple Type Vocabulary

Use a small, simple vocabulary for component input and output types.  Only expand where absolutely necessary.
- `string`
- `integer`
- `float`
- `boolean`
- `object` — JSON-like key/value map
- `list[*]` — collection of any of above


### Body Drafting Style

- **Imperative form.** "Search npm before writing a utility" beats
  "the user should consider searching npm."
- **Explain the *why*, sparingly.** A short line of reasoning beats
  a paragraph of all-caps MUSTs. LLMs reason from intent.
- **Keep the prompt lean.** Skill bodies that feel padded waste
  tokens on every invocation.
- **No surprises.** Body contents should match what `description`
  promises.
- **Quote YAML booleans used as labels.** `yes`, `no`, `on`, `off`,
  `true`, and `false` parse as booleans, not strings. As choice labels
  or branch keys, write them quoted (`"yes": ...`) or pick
  another label.

## Distillation Procedure

Checklist. Follow sequentially.

1. First read the [skill creation best practices guide](references/skill-creation-best-practices.md) and follow that same spirit here in addition to above guidance.
2. Identify source materials for domain-specific context
3. Lock the skill name
    - Ask the user what to call the skill. The name is short and slightly descriptive — it becomes the folder name. Lowercase kebab-case, <65 chars, no leading/trailing/consecutive hyphens.
    - Offer a multiple-choice list of recommendations plus a free-text option. If they type their own, validate against the rules above; on failure, state why and offer fresh suggestions plus free-text. Repeat until valid.
4. Scaffold skill directory at `./<skill-name>/` in the current working directory (not `/tmp`)
    ```shell
    skill-name/
    ├── SKILL.md                       # Required: metadata + instructions
    ├── source/                        # Required: the canonical human-readable material this skill was compiled from
    ├── scripts/                       # Optional: executable code
    ├── assets/                        # Optional: templates, resources
    ├── references/                    # Optional: documentation
    └── ...                            # Any additional files or directories
    ```
    fill in the /source materials with
    - reference docs you will use to create the skill (domain-specific context).  including
      - a source SKILL.md a user provided
      - a README.md outlining you logic from above and intent of the skill
      - Any other documentation or reference you will use
    Also populate the following at the skill folder root if the skill needs them:
    - `scripts/` — executable code the skill invokes (e.g., validators, processors).
    - `assets/` — templates, output formats, or other resources the skill references.
    - `references/` — supporting documentation the skill loads on demand (progressive disclosure).
5. Create and review `SKILL.md`
   1. Draft `SKILL.md` at the skill folder root using the source materials. Choose each component kind per Best Practices.
         - Frontmatter: `name`, `description`
         - Body
   2. Review the `SKILL.md` against this checklist. Re-run after every edit to `SKILL.md` or to the skill's files.
      - Frontmatter has `name` and `description`. `name` equals the folder name, is lowercase kebab-case, and is under 65 characters. `description` says what the skill does and when to use it.
      - Body has Trigger When and Purpose sections and is under 500 lines and roughly 5000 tokens.
      - Every relative path in the body resolves to a file in the skill folder. Every file under `scripts/`, `assets/`, and `references/` is referenced from the body with a note on when to load it.
      - Every script runs on a sample input with its declared launch command and exits 0.
      - Every decision question has a type, instructions, and criteria that separate its answers from each other.
      - Each component is the kind the priority order in Choose Component Kinds calls for, and `source/README.md` records the choice and why.
      Classify each failure:
        - **Trivial** (typo, missing field, formatting drift, dead path): fix silently and re-check.
        - **Substantive** (a component of the wrong kind, a rule left in prose that should be a script, a decision whose criteria overlap): surface it in plain language with your proposed fix; confirm before retrying.
   3. Once the review passes, run a thorough completeness check where you check for dropped logic or key context that was left out from the source. Walk the source line by line. For each distinct piece of source content:
      1. Find it in the body: a field, a component description, a question, a template, a reference, or a script. Note where. If it is there, move on.
      2. If it is not there, it was dropped. Decide which, and act:
         - **Erroneous drop** — the skill can and should carry it. Re-author the body to include it. Expect this case.
         - **Deliberate drop** — not actionable (background, history, rationale) or redundant. Record it in `source/README.md` with rationale.

      The check passes when every source item has been found in the body or recorded as a deliberate drop. Rules, conditions, thresholds, lookups, branching, and the context needed to apply them are never deliberate drops.
   4. Functional test the skill.
      1. Run it with realistic start inputs: answering the decision questions and performing the client tasks. Run it through to the end. Use enough inputs to reach every branch of the logic at least once.
      2. Spawn a fresh agent if possible, i.e. Agent/Task tool if present, `claude -p` via bash, or whatever the runtime exposes. Spawn 2–3 fresh sessions against the skill folder using prompts derived from `Trigger When` and `Purpose` sections. For each session, capture script errors and the final response.
      3. Evaluate against:
         - **Script errors** — non-zero exits, stderr noise, exceptions
         - **Decision quality** — answers and confidences on the test inputs make sense; the genuinely ambiguous cases get flagged and no others.
         - **Quality** — response matches what `description` promises; no missing sections, no hallucinated steps.
         - **Intent capture** — the response addresses the prompt's stated need, not an adjacent one.
         - **Over-restriction** — compare against what agent reasoning would produce unaided. If a script or decision stripped reasoning, nuance, or form that mattered, revise it or convert the component to a decision or client task.
         - **Correctness** — run each script against the task's actual example inputs and expected outputs, not just "no errors". Verify it produces the right result on known cases; logic bugs (e.g. a wrong key mapping in a conditional) only surface against real fixtures.

      If the runtime truly cannot spawn fresh agents, test functionally yourself and tell user: *"Functional testing not conducted with fresh agents — runtime does not support fresh agent invocation"*
   5. Iterate until the review checklist passes, every source item is classified, AND the skill passes functional test.
6. Install
   1. Ask the user what to do next:
      - **Install now** — proceed below.
      - **Iterate further** — keep editing the skill folder in place.
      - **Leave it as-is** — the skill folder stays in the current working directory. Tell them the path and stop.
   2. If installing, confirm the location with the user. Standard Agent Skills locations:
      - **Project-local** — the host agent's project skills directory (e.g., `./.claude/skills/<name>/` for Claude Code). Default if CWD is in a git repo.
      - **User-global** — the host agent's user-wide skills directory (e.g., `~/.claude/skills/<name>/` for Claude Code). Default otherwise.
   3. If a folder already exists at the destination, ask before overwriting.
   4. Move `./<skill-name>/` → `<install-location>/<skill-name>/` (folder name must equal `name` in frontmatter).
   5. Tell the user the install path. Project-local installs may need a fresh agent session to activate.

## Anti-Patterns

1. Dropping content from original SKILL.md to over compress a SKILL.md
2. Encoding rules, lookup tables, numeric calculations/thresholds, or other scriptable logic as prose instead of via scripts; or leaving to free-form reasoning a judgment a decision component can make.