# Maven dependency XML patterns

Reference snippets for the most common pom.xml dependency edits. Loaded on
demand by the procedure when an edit shape is needed.

## Basic dependency

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.2.0</version>
</dependency>
```

## Scoped dependency

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.1</version>
    <scope>test</scope>
</dependency>
```

## Optional dependency

```xml
<dependency>
    <groupId>com.google.code.findbugs</groupId>
    <artifactId>jsr305</artifactId>
    <version>3.0.2</version>
    <optional>true</optional>
</dependency>
```

## Property-based version

```xml
<properties>
    <spring-boot.version>3.2.0</spring-boot.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>${spring-boot.version}</version>
    </dependency>
</dependencies>
```

## Version range syntax

| Notation        | Meaning                  |
|-----------------|--------------------------|
| `1.0.0`         | Soft requirement — first match wins. Prefer this. |
| `[1.0.0]`       | Hard requirement — exactly 1.0.0. |
| `[1.0.0,)`      | 1.0.0 or higher.         |
| `(,1.0.0)`      | strictly less than 1.0.0.|
| `[1.0.0,2.0.0]` | inclusive range.         |
| `(1.0.0,2.0.0)` | exclusive range.         |
| `LATEST`        | **Avoid.** Non-reproducible, removed in Maven 4. |
| `RELEASE`       | **Avoid.** Same reason.  |

## Excluding a transitive dependency

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

After excluding, add the alternative as a normal dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

## Excluding logging facades

A frequent source of duplicate-class or `NoClassDefFoundError` failures:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-log4j2</artifactId>
</dependency>
```

## Forcing a version via `<dependencyManagement>`

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.9</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```
