# Plugin Failure Diagnosis Playbook

A field guide mapping common Maven build failures back to the plugin whose configuration needs to change. Use after `scripts/diagnose_plugin.sh` has surfaced the failing plugin and goal; this file translates the error into a fix.

## Triage signals

When reading Maven output, the line `[ERROR] Failed to execute goal <groupId>:<artifactId>:<version>:<goal>` names the failing plugin directly. The next `[ERROR]` lines carry the underlying cause. The fix lives in that plugin's `<configuration>` block — or in adding the plugin to `pluginManagement` if the failure is "no version specified".

## Compiler failures — `maven-compiler-plugin`

- `invalid target release: 17` or `release version N not supported` — JDK at build time is older than `<release>`. Either upgrade the JDK or lower `<release>`/`<source>`/`<target>`.
- `error: cannot find symbol` for a generated class (e.g., `AutoValue_Foo`, `Foo_Factory`, `Dagger…`) — annotation processor never ran. Add the processor under `<annotationProcessorPaths>` (see `core-build-plugins.md` § Compiler Plugin). On Java 9+, do NOT rely on the processor being on the plain classpath.
- `bad source file: …Generated…java` — competing copies of the generated class on `src/main/java` AND `target/generated-sources`. Either delete the checked-in copy or exclude the generated-sources directory.
- `error: package … does not exist` only when building the parent — wrong module reactor order or a missing `<dependency>` in the child POM.

## Test-phase failures — Surefire / Failsafe

- `No tests were executed!` while tests clearly exist — class name doesn't match `<includes>`. Default patterns are `**/Test*.java`, `**/*Test.java`, `**/*Tests.java`, `**/*TestCase.java`. Either rename or widen `<includes>`.
- `There was a timeout or other error in the fork` / `The forked VM terminated without properly saying goodbye` — JVM died mid-test. Raise `<argLine>` heap, drop `<forkCount>` to `1`, or turn off `reuseForks`.
- `Tests run: 0` together with `Failsafe` not firing — `failsafe:verify` not bound. The `verify` goal must be in the execution, otherwise integration test failures are reported but never fail the build.
- `Unable to load …mockito-agent` / `Could not transfer artifact` from a test fork — agent jar missing from `<argLine>`; add `-javaagent:…`.
- `OutOfMemoryError: Java heap space` during tests — bump `<argLine>-Xmx…`. The Maven JVM heap and the test-fork JVM heap are separate.

## Packaging failures — JAR / Shade / Assembly / Spring Boot

- `Invalid signature file digest for Manifest main attributes` from a shaded jar — add the `META-INF/*.SF|*.DSA|*.RSA` excludes to the shade filter (see `packaging-plugins.md` § Shade Plugin).
- `ServiceLoader` returns nothing in a shaded jar — add the `ServicesResourceTransformer`.
- `Unable to find main class` from `spring-boot:repackage` — set `<mainClass>` explicitly or ensure exactly one class with `public static void main` on the classpath.
- `Error assembling JAR: You have to use a classifier to attach supplemental artifacts` — two executions are producing the same artifact coordinates; add `<classifier>` or distinct execution IDs.

## Enforcer-rule failures — `maven-enforcer-plugin`

- `Detected Maven Version: X. Required: [Y,)` — bump local Maven or relax `requireMavenVersion`.
- `Failed while enforcing releasability` / `Dependency convergence error` — two transitive paths bring different versions of the same artifact. Resolve by pinning in `<dependencyManagement>` or excluding the older path. The skill `maven-dependency-management` covers this in depth.
- `Banned Dependencies` — a banned coordinate slipped in transitively. Find the path with `mvn dependency:tree -Dincludes=<group>:<artifact>` and exclude it.

## Static-analysis failures — Checkstyle / SpotBugs / PMD

- `Failed to execute goal …checkstyle:check` followed by violation count — either fix the violations or lower `<violationSeverity>`/relax the ruleset (last resort).
- `Could not find resource …checkstyle.xml` — relative path resolves against the working directory of the plugin (the module root, not the reactor root). Either move the config or use `<configLocation>${maven.multiModuleProjectDirectory}/checkstyle.xml</configLocation>`.
- `SpotBugs … high-priority warnings` — review the report; if a finding is a known false positive add it to `<excludeFilterFile>`.

## Version / release failures

- `versions:update-properties` does nothing — property name doesn't match the dependency's `groupId:artifactId` rule. Add a `<rules>` entry in `version-rules.xml`.
- `release:prepare` fails on SCM — `<scm>` block missing or `<tagNameFormat>` clashes with an existing tag.

## Repo-specific notes — `google/auto` family

- Modules in `google/auto` rely heavily on AutoValue/AutoService/AutoFactory as their own annotation processors. When compilation fails with missing `AutoValue_*` symbols after a Maven or JDK upgrade, the fix is almost always to declare the processor under `<annotationProcessorPaths>` in `maven-compiler-plugin`, not to add a runtime dependency.
- Bootstrapping order matters: the `value`, `service`, and `factory` modules each consume processors built by sibling modules. A clean reactor build (`mvn -fae -pl module -am install`) often resolves "package does not exist" surfacing from a stale install of a sibling.
- The legacy Travis builds in BugSwarm targeted older Java releases; if a fresh JDK is in the container, fall back to setting `<release>` (or `<source>`/`<target>`) consistent with what `pom.xml` originally declared rather than upgrading to the JDK's native release.
