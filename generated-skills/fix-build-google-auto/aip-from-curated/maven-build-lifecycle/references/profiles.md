# Maven Build Profiles

## Profile definition

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

## Profile activation from the command line

```bash
mvn install -Pproduction              # activate by name
mvn install -Pproduction,ci           # multiple
mvn install -P!development            # deactivate
```

## Activation triggers

```xml
<profile>
    <id>jdk17</id>
    <activation>
        <jdk>17</jdk>
    </activation>
</profile>

<profile>
    <id>windows</id>
    <activation>
        <os>
            <family>windows</family>
        </os>
    </activation>
</profile>

<profile>
    <id>ci</id>
    <activation>
        <property>
            <name>env.CI</name>
            <value>true</value>
        </property>
    </activation>
</profile>

<profile>
    <id>with-config</id>
    <activation>
        <file>
            <exists>src/main/config/app.properties</exists>
        </file>
    </activation>
</profile>
```

## Verifying which profiles are active

```bash
mvn help:active-profiles
```
Use this before changing a profile — `activeByDefault=true` profiles
deactivate as soon as any `-P` flag is present.
