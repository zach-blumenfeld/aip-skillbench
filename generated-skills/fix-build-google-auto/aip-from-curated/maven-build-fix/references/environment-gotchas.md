# Fixing old CI Maven builds in a container: gotchas

Facts about reproducing archived CI builds (BugSwarm-style images: Ubuntu 20.04, apt `maven`, JDKs copied into /usr/lib/jvm, jdk_switcher, `LANG=C`) that contradict reasonable assumptions.

## Locating the project
- The failed checkout usually lives at `/home/travis/build/failed/<owner>/<repo>`. The passing build is removed on purpose; do not look for it.
- The aggregator POM is not always `pom.xml`. google/auto, for example, builds from `build-pom.xml` (the image also symlinks `build.pom.xml` to it): run `mvn -f build-pom.xml ...` from the repo root. Each module (`common`, `service`, `factory`, `value`, ...) has its own `pom.xml` whose parent may be an external POM (e.g. `org.sonatype.oss:oss-parent`), so some versions are managed outside the repo.

## JDK
- `source /opt/jdk_switcher/jdk_switcher.sh && jdk_switcher use openjdk8` (also `openjdk7`, `oraclejdk8`, `openjdk6`) switches JAVA_HOME and PATH. Aliases map to /usr/lib/jvm via /etc/default/jdk-switcher. List what is really installed with `ls /usr/lib/jvm`; an alias whose directory is missing silently does nothing.
- The JDK that runs Maven and the bytecode level are separate: `maven.compiler.source/target` (or compiler plugin `<source>/<target>/<release>`) set the level. `<release>` needs JDK 9+ and maven-compiler-plugin 3.6+.
- JDK 7 speaks TLSv1 by default; Maven Central requires TLSv1.2 (`Received fatal alert: protocol_version`). Use a JDK 8 Maven run or `-Dhttps.protocols=TLSv1.2`.
- Old plugins on new JDKs: surefire < 2.22 and compiler < 3.8 misbehave on JDK 9+; javadoc on JDK 8+ enforces doclint.

## Repositories and the local cache
- Maven Central rejects `http://` with `501 HTTPS Required` (since 2020-01-15). Maven < 3.2.3 has an http Central in its super POM; override with an https `<repository>`/`<pluginRepository>` with id `central`.
- The image may ship a pre-populated cache under `/home/travis/.m2/repository`. Running as root with `HOME=/root` makes Maven ignore it and re-download (or fail offline). `run_build.py` points HOME at the populated cache automatically; do the same by hand (`HOME=/home/travis mvn ...` or `-Dmaven.repo.local=/home/travis/.m2/repository`).
- `... was cached in the local repository, resolution will not be reattempted until the update interval` is a cached failure: rerun with `-U`, or delete the `*.lastUpdated` files in that artifact's folder.
- Offline (`-o`) only works for artifacts already cached; check `~/.m2/repository/<group/path>/<artifact>/` for the versions that exist.

## Encoding
- `LANG=C`/`LC_ALL=C` makes the platform encoding ASCII. Non-ASCII source or resources then fail with `unmappable character for encoding ASCII` or `MalformedInputException` unless `project.build.sourceEncoding` is `UTF-8`.

## What counts as fixed
- The build is fixed when the original CI command (same goals and flags, same JDK) ends in BUILD SUCCESS with all modules SUCCESS and all tests run. Skipping tests or modules, ignoring failures, or relaxing quality gates does not count.
- Shell-only changes (exported variables, a switched JDK) disappear when the evaluator re-runs the build. Put durable settings in the repository: `.mvn/jvm.config` (Maven JVM options, Maven 3.3.1+), `.mvn/maven.config` (CLI options), POM properties/plugin config.
- Travis CI default commands for a Maven project with no overrides: `mvn install -DskipTests=true -Dmaven.javadoc.skip=true -B -V`, then `mvn test -B`. Here `-DskipTests` in the install step is the CI's own command, not a workaround; tests still run in the `script` step.
