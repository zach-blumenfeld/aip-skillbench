# Multi-Module Builds and Optimization

## Reactor (multi-module) options

```bash
mvn install                     # build every module in declaration order
mvn install -pl module-name -am # build module + dependencies (-am = also-make)
mvn install -pl module-name -amd # build module + dependents (-amd = also-make-dependents)
mvn install -rf :module-name    # resume from a module (after a partial failure)
mvn install -T 4                # 4 reactor threads
mvn install -T 1C               # one thread per CPU core
mvn install -ff                 # fail-fast on first module failure
mvn install -fae                # fail-at-end (build other modules anyway)
```

Module declaration in the parent POM:

```xml
<!-- parent/pom.xml -->
<modules>
  <module>common</module>
  <module>api</module>
  <module>service</module>
  <module>web</module>
</modules>
```

### Reactor build-order pitfalls

- A module that depends on another via `<dependency>` automatically moves later in the reactor — manual ordering in `<modules>` does not override this.
- If a module fails, `mvn install -rf :failed-module` resumes from there, but you lose the modules that finished out-of-process — useful only when previous work was installed to the local repo.
- `-pl module-name` without `-am` fails the moment any internal dependency isn't already in the local repo. Default to `-pl module-name -am` for ad-hoc builds.

## Build optimization

```bash
mvn install -amd                                # skip unchanged modules
mvnd install                                    # Maven Daemon (long-lived JVM, faster repeats)
mvn install -Dmaven.build.cache.enabled=true    # Maven 4+ build cache
```

### Parallel compiler

```xml
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
```

## Best practices

1. **Clean before releasing.** `mvn clean install` removes stale `target/` artifacts that may not match current source.
2. **Lock plugin versions.** Use `pluginManagement` in the parent POM; never let Maven pick "latest."
3. **Keep profiles focused.** One concern per profile; conflicting `<build>` blocks in overlapping profiles are a common silent-corruption source.
4. **Don't skip tests in CI** — `-DskipTests` is for local iteration, not for green builds.
5. **Parallel reactor builds for multi-module** (`-T 1C`) cut wall-clock dramatically when modules are independent.
6. **Pin all plugin versions** so the same source produces the same artifact across machines and dates.
7. **Document why each profile exists** — future-you (or another agent) needs to know.
