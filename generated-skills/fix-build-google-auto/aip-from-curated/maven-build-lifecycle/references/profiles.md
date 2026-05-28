# Build Profiles

Profiles let a single POM produce different builds (dev vs prod, CI vs local, OS-specific, JDK-specific). A build failure may stem from the **wrong profile being active** (or inactive) rather than from broken code — always check active profiles before editing source.

## Defining a profile

```xml
<profiles>
  <profile>
    <id>development</id>
    <activation>
      <activeByDefault>true</activeByDefault>
    </activation>
    <properties>
      <env>dev</env>
      <skip.integration.tests>true</skip.integration.tests>
    </properties>
  </profile>

  <profile>
    <id>production</id>
    <properties>
      <env>prod</env>
      <skip.integration.tests>false</skip.integration.tests>
    </properties>
    <build>
      <plugins>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-compiler-plugin</artifactId>
          <configuration>
            <debug>false</debug>
            <optimize>true</optimize>
          </configuration>
        </plugin>
      </plugins>
    </build>
  </profile>
</profiles>
```

## Activating profiles

```bash
mvn install -Pproduction           # activate by name
mvn install -Pproduction,ci        # activate multiple
mvn install -P!development         # deactivate
mvn help:active-profiles           # show what's currently on
```

## Automatic activation triggers

```xml
<!-- JDK version -->
<profile>
  <id>jdk17</id>
  <activation><jdk>17</jdk></activation>
</profile>

<!-- Operating system -->
<profile>
  <id>windows</id>
  <activation><os><family>windows</family></os></activation>
</profile>

<!-- Environment variable -->
<profile>
  <id>ci</id>
  <activation>
    <property><name>env.CI</name><value>true</value></property>
  </activation>
</profile>

<!-- File presence -->
<profile>
  <id>with-config</id>
  <activation>
    <file><exists>src/main/config/app.properties</exists></file>
  </activation>
</profile>
```

## Common profile-driven build failures

- **Plugin only configured in profile X** — build fails when X is not activated, because the plugin or its execution is missing from the effective POM. Fix: activate the profile, or move the plugin out of the profile.
- **`activeByDefault` overridden** — naming any profile with `-P` deactivates all `activeByDefault: true` profiles. Either re-list them on the command line or convert them to JDK/OS/property-based activation.
- **Conflicting properties across profiles** — two profiles set the same property to different values; the later-defined wins. Surface the active set with `mvn help:effective-pom -Pprofile-name`.
