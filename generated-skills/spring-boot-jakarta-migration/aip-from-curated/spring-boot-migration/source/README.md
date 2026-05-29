# Source materials and authoring notes — `spring-boot-migration` (AIP)

This folder is the audit trail behind the AIP-format `spring-boot-migration`
skill. It is *not* loaded at runtime — the skill agent reads `../SKILL.md`
and the bundled `../scripts/`.

## Files

- `procedure.schema.json` — the AIP schema this skill validates against
  (`https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json`).
  Bundled locally per the AIP spec so the skill is self-contained.
- `curated-SKILL.md` — verbatim copy of the curated source skill at
  `vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/spring-boot-migration/SKILL.md`.

## Schema choice

`procedure.schema.json` was the right fit on first read: this is a stepwise
build-config migration, not a rulebook or doc template. The schema cleanly
expresses scan → migrate → verify with script-backed steps, plus the
`modes` / `integrations` / `scenarios` / `anti_patterns` envelopes the
source SKILL.md naturally fills.

## What was scripted vs left as prose

Following the AIP "script the deterministic, leave judgment in prose" rule:

| Source content | Form in AIP skill | Rationale |
|---|---|---|
| Bump `spring-boot-starter-parent` version | script (`pom_migrate.py migrate`) | Deterministic regex over a fixed pom.xml fragment. |
| Set `<java.version>` | script | Same. |
| Strip deprecated JAXB / activation deps | script | Hardcoded list of (groupId, artifactId); each removal is a fixed transform. |
| Swap monolithic `jjwt` for modular trio | script | Single old artifact → fixed set of three new artifacts with known scopes. |
| Scan current pom state | script (`pom_migrate.py scan`) | Pure read, structural inspection. |
| Verify migration completeness | script (`pom_migrate.py verify`) | Fixed checklist of post-conditions; exits non-zero on residue. |
| Whether to add `jakarta.xml.bind-api` + `jaxb-runtime` | prose step (`consider-jakarta-xml-binding`) | Decision hinges on grepping source code AND interpreting whether the matches indicate direct JAXB use. Judgment, not lookup. |
| OpenRewrite recipe install + run | prose (in `modes.openrewrite` body) | One-shot Maven plugin install + `mvn rewrite:run`; the agent can paste the XML and shell command directly. Scripting an XML-merge of a plugin block buys little over the agent reading the snippet and editing once. |
| Recommended migration order (eight steps) | `search_shortcuts › Migration Order` | Reference list, not an execution path — the active steps already enforce ordering. |
| Verification commands (grep / mvn) | `search_shortcuts › Verification commands` | Agent reaches for these when verify-pom or compile-and-test fails; keeping them as prose lets the agent adapt them to the project. |

A single script file (`scripts/pom_migrate.py`) with three subcommands
covers all the deterministic work. Separate files for scan/migrate/verify
were considered and rejected — they share the same parsing and constant
tables, so consolidation wins on simplicity.

## Mapping of curated SKILL.md sections to AIP body

| Curated section | AIP placement |
|---|---|
| Update Spring Boot version | `steps.apply-pom-migrations` (script, default 3.2.0) |
| Update Java version | `steps.apply-pom-migrations` (script, default 21) |
| Remove deprecated JAXB / activation deps | `steps.apply-pom-migrations` (script) + `search_shortcuts › Deprecated Dependencies to Remove` |
| "Why remove these?" / namespace-collision rationale | `anti_patterns` (collision result framed as the mistake to avoid) |
| If you need XML binding in Spring Boot 3 | `steps.consider-jakarta-xml-binding` + `search_shortcuts › Jakarta XML binding (only if needed)` |
| Quick check / Verify removal `grep` commands | `search_shortcuts › Verification commands` + `steps.verify-pom` (the latter automates the same checks) |
| Update JWT library (jjwt) | `steps.apply-pom-migrations` (script) + `search_shortcuts › jjwt Migration` |
| Common issues › Compilation errors after upgrade | `steps.compile-and-test` + `integrations.jakarta-namespace` |
| Common issues › H2 dialect | `anti_patterns` (clarifies the source's identical "before/after" block was a presence/absence change, not a rename) |
| Common issues › Actuator endpoints | Dropped — see "Deliberate drops" below. |
| Migration commands › `sed` snippets | Replaced by `scripts/pom_migrate.py` per AIP guidance; an `anti_patterns` entry warns against multi-line sed on XML. |
| Using OpenRewrite for automated migration | `modes.openrewrite` (full plugin XML + run command preserved) |
| Verification steps | `steps.verify-pom` + `search_shortcuts › Verification commands` |
| Migration checklist | Decomposed into the `steps` graph (scan / migrate / consider-xml-binding / verify / compile / hand-off) and `search_shortcuts › Migration Order` |
| Recommended migration order | `search_shortcuts › Migration Order` |
| Sources (external links) | Dropped — see "Deliberate drops" below. |
| Cross-references to "Jakarta Namespace skill", "Spring Security 6 skill", "RestClient Migration skill" | `integrations` (jakarta-namespace, spring-security-6, restclient-migration) plus a fourth `integrations.hibernate-upgrade` for the matching sibling skill present in the task environment. |

## Deliberate drops

- **External-source URLs** (Spring Boot migration guide, OpenRewrite docs,
  Baeldung) — link-rot risk and adds tokens to every invocation without
  delivering procedure. The skill embeds the recipe ID and plugin XML
  directly, which is what the agent needs.
- **"Actuator endpoints" common issue** — the source skill flags it as a
  "review your security config" pointer without an actionable procedure.
  It's covered more concretely by the `spring-security-6` sibling skill;
  duplicating a vague warning here would dilute the skill's scope.
- **The "Issue 2: H2 Database Dialect" before/after block** — in the
  source it shows identical before/after class names, which is confusing.
  The real change is auto-detection in Hibernate 6, owned by the
  `hibernate-upgrade` sibling skill. Captured here only as an
  anti-pattern that clarifies the non-rename, to keep an agent from
  pattern-matching the source's misleading snippet.

## Functional-test coverage (intent, not runtime gate)

The skill activates on a Maven Spring Boot 2.x project with deprecated
JAXB / jjwt deps. A representative fixture lives at
`../tests/fixture_pom.xml`. End-to-end during authoring:

```
cp tests/fixture_pom.xml tests/pom.xml
python scripts/pom_migrate.py scan    tests/pom.xml   # snapshot baseline
python scripts/pom_migrate.py migrate tests/pom.xml   # apply edits in place
python scripts/pom_migrate.py verify  tests/pom.xml   # expect clean: true
```

This produced a Spring Boot 3.2.0 / Java 21 pom with deprecated deps
gone and the modular jjwt trio in place, all formatting preserved
(verified by hand).
