# Test Configuration: Surefire vs Failsafe

Surefire runs **unit tests** bound to the `test` phase.
Failsafe runs **integration tests** bound to `integration-test` and
`verify`. Failsafe's `verify` goal is what makes a failed integration
test fail the build — without it the failure is swallowed.

## Surefire (unit tests)

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

Default Surefire include patterns: `**/Test*.java`, `**/*Test.java`,
`**/*Tests.java`, `**/*TestCase.java`.

## Failsafe (integration tests)

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

Default Failsafe include patterns: `**/IT*.java`, `**/*IT.java`,
`**/*ITCase.java`.

To run integration tests you must invoke at least `mvn verify` — `mvn
test` does not trigger the `integration-test` or `verify` phases.
