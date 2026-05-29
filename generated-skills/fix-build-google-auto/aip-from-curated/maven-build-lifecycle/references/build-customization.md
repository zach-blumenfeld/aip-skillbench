# Maven Build Customization

## Source and target configuration

```xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Prefer `maven.compiler.release` on JDK 9+ — it pins both source and
target and rejects bytecode-level mismatches.

## Custom source directories

```xml
<build>
    <sourceDirectory>src/main/java</sourceDirectory>
    <testSourceDirectory>src/test/java</testSourceDirectory>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
        </resource>
    </resources>
    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
        </testResource>
    </testResources>
</build>
```

## Final name and output directories

```xml
<build>
    <finalName>${project.artifactId}-${project.version}</finalName>
    <directory>target</directory>
    <outputDirectory>target/classes</outputDirectory>
    <testOutputDirectory>target/test-classes</testOutputDirectory>
</build>
```

## Resource filtering — enable selectively

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>**/*.properties</include>
                <include>**/*.xml</include>
            </includes>
        </resource>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>**/*.properties</exclude>
                <exclude>**/*.xml</exclude>
            </excludes>
        </resource>
    </resources>
</build>
```

Filter only text formats. Filtering a wildcard `**/*` block corrupts
binaries (images, keystores, fonts) as Maven attempts UTF-8
substitution on them.

### Property substitution

```properties
# application.properties
app.name=${project.name}
app.version=${project.version}
app.environment=${env}
build.timestamp=${maven.build.timestamp}
```
