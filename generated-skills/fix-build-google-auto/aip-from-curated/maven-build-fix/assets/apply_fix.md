Fix the root cause of the Maven build failure in {project_dir}, then hand back the command to re-run.

Round {round}. Build command: `{build_command}` (JDK: `{jdk}`). Full log: {build_log_path}
Category from the log classifier: **{failure_category}** (confirmed by you: {category_matches}). Layer to fix: **{fix_layer}**.

Diagnosis (state key `diagnosis`): failing goal/module/phase, the first `[ERROR]` lines, javac errors (`compile_errors`), failing tests (`failed_tests`, `tests_summary`), reactor summary, log tail, and a `focused_command` that re-runs only the failing module and the modules it needs (`-pl :<module> -am <phase>`).

Playbook for this category:
{fix_playbook}

Static POM findings from inspection are in `pom_findings`; earlier rounds' changes are in `changes_made` if present. Fix a finding only if it causes this failure; leave unrelated ones alone so the diff stays minimal.

Check `run_notes` first: if it says the requested JDK could not be mapped or HOME was redirected, the build may not have run under the CI toolchain, and the failure can be an artifact of that. Fix the `jdk` value before touching code.

Work method:
1. Read the log around the first error yourself (`build_log_path`); the classifier only picks a starting point. Only the first error matters; later errors are usually a cascade of it.
2. Find what changed: `git -C {project_dir} log -3 --stat` and `git show` on the HEAD commit. In a CI-failure repo the breaking change is usually in the last commit; the fix normally makes that change consistent (update callers, tests, POM versions) rather than reverting it.
3. Make the smallest change that fixes the cause in the right layer:
   - build-config: POM edits. Pin versions in `<pluginManagement>`/`<dependencyManagement>` of the root/parent POM so every module inherits them; fix scopes (scope table in the dependency reference); exclusions with a comment saying why; https repository URLs.
   - main-source / test-code: edit the Java code. Fix the first javac error; for test failures read `target/surefire-reports/<Class>.txt` and decide whether the code or the test is wrong.
   - environment: JDK choice, Maven version, network/TLS, memory, HOME/~/.m2. Changes made only in your shell do not survive; encode them in the repository wherever possible (`.mvn/jvm.config` for Maven JVM flags, `.mvn/maven.config` for Maven CLI flags, POM properties, surefire `<argLine>`), or put the JDK in the `jdk` key.
   - transient: a network timeout or flaky test with no code cause. Re-run unchanged once; if it fails the same way, it is not transient.
4. Verify fast with `focused_command` (or a single test via `-Dtest=Class#method`), run from {project_dir} because its `-f` path is relative, under the same JDK, before handing back; the next step re-runs the full build command.
5. Off-limits: `-DskipTests`, `-Dmaven.test.skip=true`, `@Ignore`/deleting tests, `-fn`/`-fae`, `testFailureIgnore`, lowering coverage or quality thresholds, removing modules from `<modules>`, or widening enforcer rules. These make the build green without fixing it.

Load the references when the playbook is not enough: lifecycle, phases, profiles, multi-module reactor flags, debugging flags (`-X`, `-e`, `help:effective-pom`, `help:active-profiles`); dependency scopes, conflict resolution, BOMs, exclusions, `dependency:tree`; plugin configuration snippets (compiler, surefire, failsafe, javadoc, enforcer, quality plugins, packaging); environment gotchas.

Return JSON: {{"project_dir": "{project_dir}", "build_command": "...", "jdk": "...", "round": {round}, "changes_made": ["<file>: <what changed and why>", ...]}} (pass `round` through unchanged; the build step increments it). Keep `build_command` equal to the original CI command unless the change itself is to the command (for example adding `-f`); `changes_made` accumulates across rounds, so include earlier entries.
