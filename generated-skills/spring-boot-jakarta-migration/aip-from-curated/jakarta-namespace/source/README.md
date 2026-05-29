# Source notes — jakarta-namespace (AIP)

Compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/jakarta-namespace/SKILL.md`.

## Schema choice

`procedure.schema.json` — the source SKILL.md is a structured migration
procedure: trigger conditions, an ordered set of mechanical steps (find,
replace, verify), a stack of worked before/after examples, and a gotchas list.
The schema's `steps`, `scenarios`, and `anti_patterns` fields map cleanly onto
this shape. No new schema needed.

## Script vs prose decisions

| Logic                                                       | Backing | Why                                                                                                                                                                  |
|-------------------------------------------------------------|---------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Find every migration-candidate `javax.*` import             | script  | Deterministic grep with a fixed exclusion list (JDK packages stay on `javax`). The original SKILL.md chained `grep -v` per JDK package — script encodes that table once. |
| Decide which `javax.*` prefixes map to `jakarta.*`          | script  | Fixed lookup table from the source mapping table. Identical inputs → identical outputs.                                                                              |
| Rewrite each candidate import to `jakarta.*`                | script  | Deterministic prefix-replace sed over `import` lines. The original SKILL.md spelled out one `find … sed -i` per prefix; the script loops over the prefix list and is portable across GNU and BSD sed via `-i.bak`. |
| Verify no stray javax imports + jakarta.persistence present | script  | Verification is the same grep over the same prefix table — the failure rule is non-empty output. Includes the "entity class missing jakarta.persistence" check called out in the source as hard-required. |
| Handle persistence.xml / web.xml / property keys            | prose   | Non-Java surfaces with project-specific shapes — judgment-driven Edit work, not a fixed sed rule. Reference doc enumerates which files to look at.                   |
| Decide between scripted migration vs OpenRewrite            | prose (`one_of`) | Trade-off between bespoke scripts (fast, dependency-free) and OpenRewrite (broader coverage but needs Maven, network, and the plugin). Either is valid — agent picks one and runs to verification. |
| Final compile check                                         | prose   | One shell command (`mvn clean compile` / `mvn test`); not worth wrapping in a script.                                                                                |

## Completeness mapping (source SKILL.md → AIP body)

Every distinct piece of the source SKILL.md classified:

- **Overview paragraph** → captured in `purpose`.
- **"Packages such as javax.sql.* and javax.crypto.* will NOT change"** → encoded into the inventory and migration scripts as the JDK exclusion list, and called out in `references/package-mappings.md` § "Stays on javax".
- **Required Package Mappings table** → encoded into the migration script's `PREFIXES` array, and surfaced for humans in `references/package-mappings.md`.
- **Affected Annotations and Classes (Persistence / Validation / Servlet)** → moved to `references/package-mappings.md` for on-demand lookup.
- **Step 1 — Find All javax Imports** → `inventory-javax-imports` step, backed by `scripts/inventory_javax_imports.sh`.
- **Step 2 — Batch Replace All Namespaces** → `apply-namespace-migration` step, backed by `scripts/migrate_javax_to_jakarta.sh`.
- **Step 3 — Handle Wildcard Imports** → handled by the same script (the prefix match `javax.persistence` rewrites both `javax.persistence.Entity` and `javax.persistence.*`). Source's separate "Step 3" is redundant.
- **Critical: Entity Classes Must Use jakarta.persistence + before/after examples** → `verify-jakarta-namespace` step (entity-without-jakarta check) + worked example in `references/package-mappings.md` + a `scenarios` entry on the full entity migration.
- **Example Validation Migration / Example Servlet Migration** → `scenarios` entries with before/after.
- **Verification grep commands** → `verify-jakarta-namespace` step, backed by `scripts/verify_migration.sh`.
- **"If jakarta.persistence grep returns no results but you have JPA entities, migration is incomplete"** → encoded as the script's `entity-without-jakarta` failure row.
- **Using OpenRewrite for Automated Migration (pom.xml + mvn rewrite:run)** → captured as the OpenRewrite arm of the `apply-namespace-migration` step's `one_of`, plus the full XML config in `references/package-mappings.md`.
- **Common Pitfalls (don't change javax.sql/crypto; check tests; update XML; third-party libs; mixed namespaces)** → `anti_patterns` entries; non-Java surfaces (XML, properties) also called out in `references/package-mappings.md` § "Non-Java surfaces".
- **Sources** → dropped. The migration guide URLs don't belong in the executing agent's context; they were author-time references for the original skill.

No deliberate drops beyond the source URLs noted above.
