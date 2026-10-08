Confirm how to reproduce the failing Maven build before running it.

Project: {project_dir}
Failure report from the task: see `project_facts.failure_report` in the state (may be empty).

Inspection results (state keys):
- `project_facts`: root POM file, reactor modules, compiler levels, profiles and their activation, .travis.yml (jdk list + commands), Maven wrapper, `.mvn/` config, git HEAD/dirty files, and the environment (installed JDKs under /usr/lib/jvm, jdk_switcher, `mvn -v`, `java -version`, populated ~/.m2 repositories, settings.xml mirrors).
- `pom_findings`: static POM problems (plugins with no version, floating/range/external-SNAPSHOT versions, missing or duplicate dependency versions, undefined properties, system scope, http:// repositories). Any of these can be the cause; keep them in mind but do not fix them yet.

Suggested build command: `{build_command}`
Suggested JDK: `{jdk}` (empty = environment default)

Do this:
1. Read the task's own instructions and the failure report. If they name a build command, a JDK, or a failing module/test, they override the suggestions.
2. Otherwise prefer the command the original CI ran (`project_facts.travis.commands`; `script` is what failed, `install` ran first). Keep its flags; add `-B` (batch, no colour) and `-e` (stack traces) if missing. If the root POM is not `pom.xml` (e.g. `build-pom.xml`), the command needs `-f <file>`. If a Maven wrapper exists, use `./mvnw`.
3. JDK: use the CI's `jdk:` value as a jdk_switcher alias (`openjdk7`, `openjdk8`, `oraclejdk8`), a full JAVA_HOME path under /usr/lib/jvm, or `jdkN`. The JDK must support the project's `maven.compiler.source/target`; a JDK 7 Maven run cannot reach Maven Central over TLS (see the gotchas reference).
4. Never add `-DskipTests`, `-Dmaven.test.skip=true`, `-fae`/`-fn`, or `-Dmaven.test.failure.ignore` unless the original CI command already had them; they hide the failure instead of reproducing it. Use `-o` (offline) only if the network is unavailable and ~/.m2 is populated.
5. Logs go to `/tmp/aip-maven-build-fix` by default; set `log_dir` to put them elsewhere (never inside the repository).
6. If you ran the build yourself (for example because a full build exceeds your tool time limit), set `external_log_path` to the log file instead; the next step will then only diagnose it. Long builds: set `build_timeout_seconds`.

Return JSON: {{"project_dir": "...", "build_command": "...", "jdk": "...", "round": 0}} (`round` stays 0 here; add `log_dir` / `external_log_path` / `build_timeout_seconds` when used).
