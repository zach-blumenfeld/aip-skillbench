# Plugin Basics

## Plugin Structure

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.12.1</version>
            <configuration>
                <!-- Plugin-specific configuration -->
            </configuration>
            <executions>
                <execution>
                    <id>compile-java</id>
                    <phase>compile</phase>
                    <goals>
                        <goal>compile</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

## Plugin Management

Centralize plugin versions and shared configuration in `pluginManagement` so child modules inherit it. Declare the actual plugin under `<build><plugins>` without a version to inherit.

```xml
<build>
    <pluginManagement>
        <plugins>
            <!-- Define versions and shared config -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.12.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
    <plugins>
        <!-- Actually use plugin (inherits config) -->
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

## Best Practices

1. **Version Pinning** — Always specify plugin versions; never rely on defaults.
2. **Plugin Management** — Centralize in parent POM.
3. **Minimal Configuration** — Use defaults where possible.
4. **Execution IDs** — Use meaningful execution IDs.
5. **Phase Binding** — Bind to appropriate lifecycle phases.
6. **Skip Properties** — Provide skip properties for flexibility.
7. **Documentation** — Comment complex configurations.
8. **Inheritance** — Use `pluginManagement` for multi-module projects.
9. **Updates** — Keep plugins current.
10. **Profile Separation** — Separate CI/release plugins into profiles.

## Common Pitfalls

1. **Missing Versions** — Relying on default versions yields unstable builds.
2. **Wrong Phase** — Plugin bound to wrong lifecycle phase fires at the wrong time.
3. **Duplicate Executions** — Same goal running multiple times (often from competing executions in parent + child).
4. **Memory Issues** — Insufficient heap for plugins (raise via `argLine`).
5. **Ordering** — Plugin execution order conflicts within a phase.
6. **Inheritance** — Unintended plugin inheritance from parent POM.
7. **Fork Confusion** — Misunderstanding fork behavior (`forkCount`, `reuseForks`).
8. **Skip Flags** — Tests accidentally skipped in CI (`-DskipTests` vs `-Dmaven.test.skip`).
