# Resource Filtering and Build Customization

## Source / target / encoding

```xml
<properties>
  <maven.compiler.source>17</maven.compiler.source>
  <maven.compiler.target>17</maven.compiler.target>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Mismatched `source` / `target` / `release` between the parent and a module causes mysterious "invalid target release" or `--release` errors at `compile`. Always confirm with `mvn help:effective-pom` rather than reading the raw `pom.xml`.

## Custom directories

```xml
<build>
  <sourceDirectory>src/main/java</sourceDirectory>
  <testSourceDirectory>src/test/java</testSourceDirectory>
  <resources>
    <resource><directory>src/main/resources</directory></resource>
  </resources>
  <testResources>
    <testResource><directory>src/test/resources</directory></testResource>
  </testResources>
</build>
```

## Final artifact name and output paths

```xml
<build>
  <finalName>${project.artifactId}-${project.version}</finalName>
  <directory>target</directory>
  <outputDirectory>target/classes</outputDirectory>
  <testOutputDirectory>target/test-classes</testOutputDirectory>
</build>
```

## Resource filtering

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

Property substitution into filtered resources:

```properties
# application.properties
app.name=${project.name}
app.version=${project.version}
app.environment=${env}
build.timestamp=${maven.build.timestamp}
```

### Common pitfall

Filtering binaries (images, keystores, fonts) corrupts them silently — Maven rewrites `${...}` tokens that happen to appear inside the bytes. Always include/exclude binary file types explicitly.
