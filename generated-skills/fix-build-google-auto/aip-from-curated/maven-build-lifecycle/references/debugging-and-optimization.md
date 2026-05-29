# Debugging and Optimizing Maven Builds

## Verbose output flags

```bash
mvn install -X      # debug mode: full plugin/dependency resolution
mvn install -e      # error stacktrace
mvn install -q      # quiet mode
mvn install -ff     # fail fast in the reactor — first failure stops the build
```

## Effective POM / settings / profiles

```bash
mvn help:effective-pom       # resolved POM after inheritance + profiles
mvn help:effective-settings  # resolved settings.xml
mvn help:active-profiles     # which profiles actually activated
```
Use these BEFORE editing config. `effective-pom` shows the exact plugin
configuration that ran, including parent inheritance and active-profile
overrides — frequently surprises.

## Dependency analysis

```bash
mvn dependency:tree                          # show full dependency tree
mvn dependency:tree -Dincludes=group:artifact  # filter to one path
mvn dependency:analyze                       # used vs declared
mvn versions:display-plugin-updates          # plugin versions available
mvn versions:display-dependency-updates      # dependency versions available
```

`mvn dependency:tree` is the first probe when a "missing symbol" or
"no such method" error appears at compile/test time — frequently a
transitive version conflict.

## Parallel and incremental builds

```bash
mvn install -T 4         # 4 worker threads
mvn install -T 1C        # one thread per CPU core
mvn install -amd         # skip unchanged modules (also-make-dependents)
mvnd install             # Maven Daemon — persistent JVM, build cache
```

Parallel builds require all plugins in the reactor to be thread-safe.
A non-thread-safe plugin surfaces as flaky / non-deterministic failures
under `-T`.

### Compiler memory tuning

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <fork>true</fork>
                <compilerArgs>
                    <arg>-J-Xmx512m</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

### Build cache (Maven 4+)

```bash
mvn install -Dmaven.build.cache.enabled=true
```
