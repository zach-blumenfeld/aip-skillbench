# spring-security-6 — AIP conversion notes

## Source

Converted from the curated Agent Skill at:

    vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/spring-security-6/SKILL.md

A verbatim copy is preserved at `source/CURATED_SKILL.md`.

## Schema choice

Used the shared `procedure.schema.json` (bundled here in `source/`,
canonical at the AIP repo). The curated skill is a multi-step migration
playbook — a graph of script-backed and prose-backed nodes with declared
inputs/outputs — which is exactly what the procedure schema is for.
No new schema was drafted.

## Script-vs-prose decisions

The curated skill mixes mechanical replacements with structural rewrites.
Scripts cover the mechanical parts; prose covers the parts that require
reading and reasoning over a class body.

| Curated content | Where it lives in this AIP skill | Why |
|---|---|---|
| Per-pattern grep commands ("Find classes extending WebSecurityConfigurerAdapter", "Should return NO results", "Should return results") | `scripts/scan.sh` (discovery) and `scripts/verify.sh` (gate) | Fixed-string grep over a fixed pattern list — deterministic and the same on every run. |
| `sed` replacements for `@EnableGlobalMethodSecurity`, `antMatchers`, `mvcMatchers`, `regexMatchers`, `authorizeRequests` | `scripts/mechanical_renames.sh` | Pure textual substitution with no structural risk; making this a script ensures consistent application and lets the agent re-run idempotently. Used `perl -i` instead of `sed -i` for BSD/GNU portability. |
| Removing `WebSecurityConfigurerAdapter` and refactoring `configure()` overrides into a `SecurityFilterChain` @Bean | Prose step `refactor-config-class` | The shape of each class differs (different beans, different override signatures, different supporting methods); requires reading the class and deciding. The curated skill itself flags "cannot be automated with sed". |
| Converting chained DSL (`.csrf().disable().and()...`) to lambda DSL | Prose step `convert-lambda-dsl` | A blind sed would break parentheses balancing. The rules are short and well-suited to LLM reasoning per method. |
| `javax.servlet` → `jakarta.servlet` import rename | Deliberately dropped (mentioned in scan only) | Belongs to the broader Jakarta EE migration skill, not Spring Security 6. Recorded as `do_not_use_when` / anti-pattern. |

## Source content classification

Every section of `source/CURATED_SKILL.md` was classified:

- **Mapped**
  - "Overview" + "Key Changes" prose → captured in `purpose` and per-step `description`s.
  - "Remove WebSecurityConfigurerAdapter" before/after example → `refactor-config-class` step (rules 1–5).
  - "Method Security Annotation Change" → mechanical script + scan/verify patterns.
  - "Lambda DSL Configuration" / "Exception Handling" / "Headers Configuration" before/after examples → `convert-lambda-dsl` rules.
  - "URL Matching Changes" (antMatchers → requestMatchers) → mechanical script.
  - "UserDetailsService Configuration" guidance → `refactor-config-class` rule 3.
  - "Complete Migration Example" → represented as the first `scenarios` entry (single-class full migration).
  - "Migration Commands Summary" Steps 1–4 → mechanical script + scan/refactor steps.
  - "Verification Commands" → `scripts/verify.sh`.
  - "Common Migration Pitfalls" 1–5 → `anti_patterns` entries.

- **Deliberate drop**
  - "Servlet Namespace Change" (javax → jakarta) — out of scope for a Spring Security skill; handled by the Jakarta EE migration. Mentioned only in `do_not_use_when` and in the `scan-codebase` script's report (as a flag) so the agent knows where to look but does not act on it here.
  - "Testing Security" — informational and not security-6-specific (`@WithMockUser` works on both versions). Cutting it keeps the body lean.
  - "Sources" links (Baeldung, Spring docs) — reference links are not actionable instructions; dropping them keeps the SKILL.md body under the progressive-disclosure budget. If the agent needs to look something up, web search will surface the same canonical pages.
  - The bare `bash` heredoc-style `sed -i` commands embedded in prose — replaced by `scripts/mechanical_renames.sh` which is portable and idempotent. The shell-flavor-fragile commands themselves are gone on purpose.

- **Schema gap / Body drop**: none. The procedure schema accommodated every piece of mapped content.

## Anti-patterns added beyond the source

`anti_patterns` includes two items not in the source's "Common Migration Pitfalls":

- Blind sed for lambda DSL conversion — added because the script
  deliberately omits this and the agent might otherwise try.
- Bundling the javax→jakarta rename into this skill — added because
  splitting that scope is a key boundary of this skill.

These keep the agent from mistakes the structural choices here would
otherwise enable.
