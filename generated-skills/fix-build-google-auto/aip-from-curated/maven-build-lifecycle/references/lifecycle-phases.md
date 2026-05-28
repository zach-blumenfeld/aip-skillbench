# Maven Lifecycle Phases

Maven has three independent lifecycles: **default** (the build), **clean**, and **site**. A phase invocation runs every preceding phase in its lifecycle. Diagnosing a build failure starts with locating the failing phase on this list — every phase before it has already succeeded.

## Default Lifecycle (in order)

```
 1. validate                 — Validate project structure
 2. initialize               — Initialize build state
 3. generate-sources
 4. process-sources
 5. generate-resources
 6. process-resources        — Copy resources to output
 7. compile                  — Compile source code
 8. process-classes
 9. generate-test-sources
10. process-test-sources
11. generate-test-resources
12. process-test-resources
13. test-compile             — Compile test sources
14. process-test-classes
15. test                     — Run unit tests
16. prepare-package
17. package                  — Create JAR/WAR
18. pre-integration-test
19. integration-test         — Run integration tests
20. post-integration-test
21. verify                   — Run verification checks
22. install                  — Install to local repo
23. deploy                   — Deploy to remote repo
```

### Common invocations

```bash
mvn compile                          # 1–7
mvn test                             # 1–15
mvn package                          # 1–17
mvn install                          # 1–22 (local repo)
mvn deploy                           # 1–23 (remote repo)
mvn clean install                    # clean lifecycle, then default 1–22
mvn install -DskipTests              # skip running tests (still compile them)
mvn install -Dmaven.test.skip=true   # skip compiling AND running tests
```

## Clean Lifecycle

```
1. pre-clean
2. clean          — Delete target directory
3. post-clean
```

```bash
mvn clean
mvn clean -DbuildDirectory=out
```

## Site Lifecycle

```
1. pre-site
2. site           — Generate documentation
3. post-site
4. site-deploy    — Deploy documentation
```

```bash
mvn site
mvn site-deploy
```

## Phases vs goals

- **Phase**: a stage in a lifecycle. Invoking it runs every preceding phase in the same lifecycle.
  - `mvn package` ⇒ runs phases 1–17 of the default lifecycle.
- **Goal**: a single plugin operation. Invoking it runs only that goal — no surrounding lifecycle.
  - `mvn compiler:compile` ⇒ runs only the compiler plugin's compile goal.
  - `mvn surefire:test` ⇒ runs only Surefire's test goal.
  - `mvn jar:jar` ⇒ packs a JAR from existing `target/classes` without compiling first.

Multiple goals on one command: `mvn dependency:tree compiler:compile`.

### Phase-to-goal bindings (pom.xml)

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.12.1</version>
      <executions>
        <execution>
          <id>compile-sources</id>
          <phase>compile</phase>
          <goals><goal>compile</goal></goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```
