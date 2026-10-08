# maven-build-fix — provenance and compilation notes

## Sources (copied verbatim into this folder)

| File | Origin |
|---|---|
| `maven-build-lifecycle/SKILL.md` | Han `jutsu-maven` skill (TheBushidoCollective/han @ 8b5dd72), curated input |
| `maven-dependency-management/SKILL.md` | same |
| `maven-plugin-configuration/SKILL.md` | same |
| `environment-Dockerfile` | the task container's Dockerfile (BugSwarm image `google-auto-101506036`: Ubuntu 20.04, apt `maven`, JDKs copied to /usr/lib/jvm, jdk_switcher, `LANG=C`, failed checkout under /home/travis/build/failed, `build-pom.xml` symlinked as `build.pom.xml`) |
| `environment-README.md` | the task environment note naming the Han skills as the origin |

No `inputs/environment/data/` existed, so no input files constrain loaders. The task type is "repair a failing Maven CI build"; the three sources are general Maven reference material, so they were compiled into one fix-and-rebuild loop and the full source text was kept as on-demand references.

## Intent

The three skills describe one workflow when the consumer is an agent asked to fix a broken build: understand the reactor and lifecycle (build-lifecycle), resolve dependency problems (dependency-management), and configure or pin plugins (plugin-configuration). The procedure is: inspect → confirm command/JDK → run + classify → judge layer → fix → re-run, until green or the round limit.

## Graph and step-kind choices

| Step | Kind | Why |
|---|---|---|
| `inspect-project` | execution (`scripts/inspect_project.py`) | Finding the aggregator POM, walking `<modules>`, reading compiler levels/profiles/.travis.yml, listing JDKs and ~/.m2, and linting POMs are deterministic. The lint rules are the sources' best practices and pitfalls turned into checks: missing plugin versions (Version Pinning / Missing Versions), LATEST/RELEASE and version ranges (Avoid Version Ranges), external SNAPSHOTs (Snapshot in Production), system scope (System Scope pitfall), duplicate declarations (banDuplicatePomDependencyVersions), missing dependency versions without dependencyManagement, undefined `${property}` versions (Property-Based Versions), http repositories. |
| `confirm-build` | client_task | Choosing the reproduction command needs the task's own instructions, which the script cannot see; the script supplies a default (CI `script` command, else Travis's default commands, else `mvn -B -e clean install`, with `-f` for non-`pom.xml` aggregators). |
| `run-build` | execution (`scripts/run_build.py` + `assets/failure_catalog.json`) | Running the command under a JDK and parsing the log is mechanical: `Failed to execute goal` coordinates → module, goal, and phase (via the phase-to-goal binding table from the lifecycle source), javac errors, failed tests, reactor summary, and a catalog lookup that maps error patterns to a category with a playbook. It also builds the focused rerun command (`-pl :module -am <phase>`, from the Reactor Options section), enforces the round limit, and flags skip flags added after round 1 (Skipping Tests / Skip Flags pitfalls). |
| `by-outcome` | router | Branches on `build_outcome` (passed / failed / exhausted). |
| `assess-cause` | decision | Two judgments with a fixed answer space: does the classifier's category match the first real error (noul), and which layer must change (choice: build-config, main-source, test-code, environment, transient). The second is the key judgment that keeps fixes in the right place (e.g. not editing code for a JDK mismatch). |
| `apply-fix` | client_task | Writing code/POM edits is generation. The template carries the work method, the per-layer rules, the off-limits list, and pointers to the references. Loops back to `run-build`. |
| `report` | client_task | Summary text. |

Loop safety: `max_rounds` (8) in the catalog; `run-build` returns `exhausted` at the limit.

Log location: `run_build.py` writes logs to `/tmp/aip-maven-build-fix` by default (never inside the repo, so the fix diff stays clean); the `log_dir` state key overrides it.

## Where source content lives in the pack

- `references/build-lifecycle.md`, `references/dependency-management.md`, `references/plugin-configuration.md`: the three source bodies, verbatim (frontmatter removed). Every snippet, table, command, best practice, and pitfall stays reachable on demand from `confirm-build` and `apply-fix`.
- Phase order and phase-to-goal bindings → `failure_catalog.json` (`phase_order`, `goal_phase`) → `failing_phase` and `focused_command`.
- Common phase commands and skip options → the `SKIP_FLAGS` guard in `run_build.py`, the `confirm_build.md` rule 4, and the anti-patterns.
- Profiles and activation triggers (jdk/os/property/file) → `project_facts.profiles` from inspection.
- Resource filtering and encoding → catalog `resources` playbook.
- Source/target/release → `project_facts.compiler_levels`, JDK hint, `jdk-mismatch` playbook.
- Reactor options, module order, resume (-rf) → `focused_command`, `reactor-order` playbook.
- Surefire/failsafe configuration → `test-failure`, `test-fork-crash` playbooks and the plugin reference.
- Build optimization (parallel -T, compiler fork/-J-Xmx) → `out-of-memory` playbook.
- Debugging (-X, -e, help:effective-pom, help:active-profiles, help:effective-settings) → `apply_fix.md`, the `unknown` playbook, `pom-invalid` playbook.
- Scope table, optional dependencies → `compilation` playbook (wrong scope, optional not transitive) and the dependency reference.
- dependencyManagement/BOM import, forcing versions, nearest-wins → `dependency-resolution`, `enforcer`, `pom-invalid` playbooks and the missing-version lint.
- Exclusions (with documented reason) → playbooks and an anti-pattern.
- dependency:tree/-Dverbose/-Dincludes, dependency:analyze, -U, purge-local-repository → `dependency-resolution` playbook and the dependency reference.
- Enforcer rules → `enforcer` category (and `maven-version`/`jdk-mismatch` for requireMavenVersion/requireJavaVersion).
- Repositories / settings.xml → http-repository lint, `repository-https-required` playbook, `settings_mirrors` in inspection.
- Plugin structure, pluginManagement inheritance, version pinning → lint rule, `plugin-resolution` playbook, `apply_fix.md` build-config rule, anti-patterns.
- Compiler (release, annotationProcessorPaths) → `jdk-mismatch` and `annotation-processing` playbooks.
- Javadoc (doclint) → `javadoc` playbook. JaCoCo, checkstyle, SpotBugs, PMD → `quality-gate` playbook and anti-pattern against lowering thresholds.
- Jar/source/assembly/shade/war, profile separation for release plugins → `packaging` playbook.
- Best practice "Use Clean Builds" / pitfall "Missing Clean" → `compilation` playbook (stale target/).
- Pitfall "Duplicate classes / Missing Exclusions" → `dependency-resolution` playbook.
- "When to Use This Skill" lists → `trigger_when` and the frontmatter description.

Added beyond the sources (from the task's Dockerfile and general CI-repair practice): `references/environment-gotchas.md` (jdk_switcher, JDK 7 TLS, HTTPS-only Central, /home/travis ~/.m2, LANG=C, non-`pom.xml` aggregators, Travis default commands, what counts as fixed) and the HOME-to-populated-~/.m2 logic in `run_build.py`.

## Deliberate drops (not carried into the procedure body; still present verbatim in references/)

| Source item | Why not in the procedure |
|---|---|
| Overview / intro paragraphs of all three skills | Background; no action. |
| Site lifecycle details, `mvn site-deploy` | Not part of repairing a CI build; kept in the reference. |
| Custom source directories, final name/output directory snippets | Configuration examples with no failure mode of their own; the reference has them. |
| Build cache (Maven 4+), mvnd | Not available in the target container (apt Maven 3.6). |
| CI/CD snippets (GitHub Actions, Jenkins) | Examples of commands; the `-B` batch flag they teach is carried in `confirm_build.md`. |
| Spring Boot plugin, release plugin, versions plugin update goals | Feature/release tooling, not needed to fix a build; reference only. |
| "Regular Updates", "Keep plugins current", "Outdated Dependencies" | Upgrading for its own sake widens the diff and risks new breakage; the procedure pins to what works. |
| Execution IDs, document profiles, comment complex config | Style advice; the exclusion-comment rule is kept as an anti-pattern. |
