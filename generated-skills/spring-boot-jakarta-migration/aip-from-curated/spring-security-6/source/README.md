# AIP authoring notes — spring-security-6

## Source

`original-SKILL.md` is the curated Agent Skill from
`vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/spring-security-6/SKILL.md`,
copied verbatim. The skill is part of the SkillsBench
`spring-boot-jakarta-migration` task and the `name:` frontmatter must
remain `spring-security-6` to mount correctly at task runtime.

## Schema choice

`procedure.schema.json` — the source is a structured multi-step migration
runbook with explicit ordered steps, verification gates, and worked
before/after examples. Procedure is the right shape: nodes (steps),
backed by scripts where possible (mechanical substitutions, scans, and
verification), plus `scenarios` for the worked examples and
`anti_patterns` for the pitfall list.

## Script-backing decisions

The source had a large block of shell `sed`/`grep` snippets. AIP best
practice says scriptable logic — substitutions, lookup tables, presence
checks — must live in `scripts/`, not prose. The three substitution
scripts (`migrate_mechanical.py`, `migrate_servlet_imports.py`) and two
inspection scripts (`scan_legacy_patterns.py`, `verify_migration.py`)
replace those shell snippets with cross-platform Python that runs
identically on macOS/Linux/Windows and emits structured JSON the agent
can act on.

Two pieces of work resist scripting and remain as prose-backed steps
that load `references/refactor-templates.md`:
- Removing `WebSecurityConfigurerAdapter` — structural class refactor.
- Converting chained DSL to lambda DSL — context-dependent rewriting.

## Source-to-body classification

Every distinct piece of the original `SKILL.md` was classified.

### Mapped (captured in the AIP body or its scripts/references)

- Overview of Spring Security 6 / `SecurityFilterChain` → `purpose`.
- Activation triggers (matchers, adapter removal, lambda DSL,
  `@EnableGlobalMethodSecurity` swap) → `trigger_when`.
- WebSecurityConfigurerAdapter before/after example →
  `references/refactor-templates.md` (Template 1) + `scenarios[0]`.
- Method security annotation change (annotation + import + sed command +
  verification grep) → `steps.migrate-mechanical` (script handles
  annotation + import) and `steps.verify-migration` (script handles
  presence/absence).
- Lambda DSL conversion (CSRF, cors, sessionManagement, headers,
  exceptionHandling, authorizeHttp) → `steps.convert-lambda-dsl` +
  `references/refactor-templates.md` (Template 2).
- antMatchers/mvcMatchers/regexMatchers → requestMatchers →
  `steps.migrate-mechanical` (script).
- authorizeRequests → authorizeHttpRequests → `steps.migrate-mechanical`
  (script).
- Exception handling and headers conversion → Template 2.
- UserDetailsService auto-detection → `references/gotchas.md` #4 +
  Template 4.
- Complete migration example → `references/refactor-templates.md`
  Template 1 + `scenarios[1]`.
- Servlet namespace `javax → jakarta` → `steps.migrate-servlet-imports`
  (script) + Template 3.
- Testing security note (`@WithMockUser`) → Template 5 (the original
  signal is that nothing changes; the template documents that).
- Migration commands summary (shell sed) → captured by Python
  substitution scripts.
- Verification commands (legacy + new presence greps) → captured by
  `verify_migration.py`.
- Common pitfalls #1–#5 → `anti_patterns` + matching entries in
  `references/gotchas.md` (which adds nuance the original elided —
  e.g. defaults differing between `@EnableGlobalMethodSecurity` and
  `@EnableMethodSecurity`).
- Sources (Baeldung, Spring docs) → not propagated to the AIP body to
  keep token cost low; preserved here in `original-SKILL.md` for
  reference.

### Deliberate drops

- External citation URLs (Baeldung, Spring docs). Rationale: not load-
  bearing for an agent executing the migration; the procedure itself is
  self-contained. Preserved in `original-SKILL.md`.
- The literal `find ... -exec sed -i ...` shell incantations.
  Rationale: replaced by Python scripts that work on macOS (BSD sed) as
  well as Linux. The shell forms remain in `original-SKILL.md`.

### Schema gaps

None encountered. The procedure schema accommodated every piece of
load-bearing content (steps, scenarios, anti_patterns, references).
