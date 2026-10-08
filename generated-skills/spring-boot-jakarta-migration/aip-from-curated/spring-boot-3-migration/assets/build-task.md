# {meta.name}: compile and test on Java 21

Project root: {project_dir}

Static verification passed. Final static checks:

{static_checks}

Build and test the migrated project. Load `references/boot-3-build.md` (section "Build and
test in the task container") for the exact environment setup.

1. Make sure Maven runs on Java 17+ (Java 21 preferred): in the task container
   `source /root/.sdkman/bin/sdkman-init.sh` and `sdk use java 21.0.2-tem`; check
   `java -version` and `mvn -v`. Use `./mvnw` when the project has one. Outside that
   container (no `/root/.sdkman`), use any JDK 17+ on the host via `JAVA_HOME`; the inventory's
   `maven_executable`, `maven_wrapper` and `jdks` show what the scan found.
2. From the project root run `mvn -B clean compile`, then `mvn -B test`.
3. When compilation or a test fails because of the code, fix it right away and rerun, as long
   as the fix is small and clearly part of the migration (a missed import, a jakarta class, a
   lambda DSL detail, a RestClient generic). Load the matching reference for the area. Larger
   problems: stop and report them.
4. Do not skip tests (`-DskipTests`, `@Disabled`), delete tests, or downgrade versions to get
   a green build.
5. If Maven cannot resolve Boot 3 artifacts because there is no network or the repository is
   unreachable, try `mvn -o` once, then stop. That is an environment limit, not a code error.

Output for the next step: `build_report` (string) — the commands you ran, the JDK and Maven
versions, compile result, test totals (run/failures/errors/skipped), the first error verbatim
for any failure, and every file you changed in this step.
