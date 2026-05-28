# Test Execution and Packaging

Failures in phases 13–21 (`test-compile`, `test`, `package`, `integration-test`, `verify`) usually point to test or plugin configuration rather than source-code bugs in `src/main/`.

## Surefire — unit tests (phase: `test`)

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.2.3</version>
  <configuration>
    <includes>
      <include>**/*Test.java</include>
      <include>**/*Tests.java</include>
    </includes>
    <excludes>
      <exclude>**/*IntegrationTest.java</exclude>
    </excludes>
    <parallel>methods</parallel>
    <threadCount>4</threadCount>
    <forkCount>1</forkCount>
    <reuseForks>true</reuseForks>
  </configuration>
</plugin>
```

### Skip options (know the difference)

```bash
mvn install -DskipTests              # compile tests, don't run them
mvn install -Dmaven.test.skip=true   # don't even compile tests
mvn install -Dtest=ClassA#methodB    # run a single test method
```

`maven.test.skip=true` also skips `test-compile`, so a broken test class won't surface — only use it when you've confirmed the failure is *not* in tests.

## Failsafe — integration tests (phases: `integration-test`, `verify`)

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <version>3.2.3</version>
  <executions>
    <execution>
      <goals>
        <goal>integration-test</goal>
        <goal>verify</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <includes>
      <include>**/*IT.java</include>
      <include>**/*IntegrationTest.java</include>
    </includes>
  </configuration>
</plugin>
```

Failsafe runs in `integration-test` but the **failure is only reported at `verify`** — running `mvn integration-test` alone hides failures. Always go through `mvn verify` (or `mvn install`).

## Packaging gotchas

- A `package` failure on shaded/assembly plugins usually means a missing dependency or duplicate-resource conflict — `mvn package -X` shows the merge map.
- `package` runs after `test`. If tests pass locally but `package` fails in CI, look at the package-step plugins (shade, assembly, war), not the source.
- Snapshot artifacts at release time → fail the build with the Enforcer plugin; never let `mvn deploy` push a SNAPSHOT to a release repo.
