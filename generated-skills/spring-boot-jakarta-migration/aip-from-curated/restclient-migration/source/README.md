# Source notes — restclient-migration (AIP)

Compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/restclient-migration/SKILL.md`.

## Schema choice

`procedure.schema.json` — the source SKILL.md is a structured migration procedure:
trigger conditions, ordered steps, and a stack of worked examples (GET, POST, DELETE,
exchange-with-headers, error handling, full service). The schema's `steps`,
`scenarios`, and `anti_patterns` map this cleanly. No new schema needed.

## Script vs prose decisions

| Logic                                                | Backing | Why                                                                                                                                                |
|------------------------------------------------------|---------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| Find every RestTemplate call site in the workspace  | script  | Deterministic grep over files; same input → same output. `scripts/inventory_call_sites.sh` emits one row per match with file:line and method hint. |
| Classify each call site (which RestTemplate idiom)   | prose   | Requires reading the surrounding Java — judgment over real code, not a fixed lookup.                                                                |
| Pick the matching RestClient pattern                 | prose   | One-to-many mapping with stylistic choices (inline vs configured base URL, `body(Class)` vs `body(ParameterizedTypeReference)`). Reference table loaded on demand from `references/api-mappings.md`. |
| Apply the transformation in Java                     | prose   | Java edits — Edit tool, agent judgment.                                                                                                            |
| Verify (`mvn clean compile`, `mvn test`)             | prose   | One shell command per gate; trivial enough that a script would just wrap it.                                                                       |

## Completeness mapping (source SKILL.md → AIP body)

Every distinct piece of the source SKILL.md classified:

- **Overview / Key Differences table** → captured as the `purpose` paragraph + dropped table (redundant once examples carry the contrast). See `references/api-mappings.md` for the full table — loaded on demand.
- **Basic GET / POST / Exchange / DELETE before-after pairs** → `scenarios` entries with `need` / `context` / `action` / `outcome`, plus reference doc.
- **RestClient Configuration (`@Bean` + builder)** → `configure-restclient-bean` step + dedicated scenario.
- **Error Handling (onStatus)** → `add-error-handlers` step + dedicated scenario.
- **Type-Safe Responses (ParameterizedTypeReference vs Class)** → captured in `references/api-mappings.md` and called out in the `apply-migration-pattern` step.
- **Complete Service Migration Example** → `scenarios` entry with the full before/after.
- **WebClient Alternative** → captured in `do_not_use_when` (reactive apps) + `anti_patterns`. Code sample dropped — pointing to WebClient is enough; full reactive examples don't belong in this skill.

No deliberate drops beyond the WebClient code sample noted above.
