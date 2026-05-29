# Version Management & Code Generation Plugins

## Versions Plugin

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>versions-maven-plugin</artifactId>
    <version>2.16.2</version>
    <configuration>
        <rulesUri>file:///${project.basedir}/version-rules.xml</rulesUri>
    </configuration>
</plugin>
```

```bash
# Check for updates
mvn versions:display-dependency-updates
mvn versions:display-plugin-updates
mvn versions:display-property-updates

# Update versions
mvn versions:update-properties
mvn versions:use-latest-releases
mvn versions:update-parent
```

## Release Plugin

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-release-plugin</artifactId>
    <version>3.0.1</version>
    <configuration>
        <tagNameFormat>v@{project.version}</tagNameFormat>
        <autoVersionSubmodules>true</autoVersionSubmodules>
        <releaseProfiles>release</releaseProfiles>
    </configuration>
</plugin>
```

## Build Helper Plugin

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>add-source</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>add-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>${project.build.directory}/generated-sources</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Use when annotation processors or codegen drop sources outside `target/generated-sources/annotations` and they need to be re-added to the compile path.

## Exec Plugin

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.1.1</version>
    <executions>
        <execution>
            <id>run-script</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>exec</goal>
            </goals>
            <configuration>
                <executable>bash</executable>
                <arguments>
                    <argument>${project.basedir}/scripts/generate.sh</argument>
                </arguments>
            </configuration>
        </execution>
    </executions>
</plugin>
```
