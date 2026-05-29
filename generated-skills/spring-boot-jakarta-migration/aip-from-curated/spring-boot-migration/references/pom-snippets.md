# pom.xml snippets — Spring Boot 2.x → 3.x

Reference snippets the agent assembles into `pom.xml` edits. Load only when the
agent reaches the corresponding step.

## 1. Spring Boot parent version

```xml
<!-- Before: Spring Boot 2.7.x -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>2.7.18</version>
</parent>

<!-- After: Spring Boot 3.2.x -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
</parent>
```

## 2. Java version property

Spring Boot 3 requires Java 17+. Prefer 21 for new work.

```xml
<properties>
    <!-- Before -->
    <java.version>1.8</java.version>

    <!-- After -->
    <java.version>21</java.version>
</properties>
```

## 3. Deprecated dependencies to REMOVE

These conflict with Jakarta EE on the classpath and must be deleted outright.
Spring Boot 3 transitively brings the Jakarta XML Bind APIs when something on
the classpath needs them.

```xml
<!-- REMOVE ALL of these -->

<!-- Old JAXB API -->
<dependency>
    <groupId>javax.xml.bind</groupId>
    <artifactId>jaxb-api</artifactId>
</dependency>

<!-- Old JAXB implementation -->
<dependency>
    <groupId>com.sun.xml.bind</groupId>
    <artifactId>jaxb-impl</artifactId>
</dependency>

<dependency>
    <groupId>com.sun.xml.bind</groupId>
    <artifactId>jaxb-core</artifactId>
</dependency>

<!-- Old Java Activation -->
<dependency>
    <groupId>javax.activation</groupId>
    <artifactId>activation</artifactId>
</dependency>

<dependency>
    <groupId>javax.activation</groupId>
    <artifactId>javax.activation-api</artifactId>
</dependency>
```

### Why remove these?

1. **Namespace conflict.** `javax.xml.bind` is Java EE; Spring Boot 3 uses
   Jakarta EE's `jakarta.xml.bind`. Both on the classpath → `ClassNotFoundException`
   and other runtime errors.
2. **Spring Boot 3 already pulls Jakarta XML Bind transitively** when needed.
3. **Build failures.** Mixed namespaces produce broken builds even when
   compilation appears to succeed.

### Jakarta replacements (only if XML binding is actually used)

```xml
<dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
</dependency>
<dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
</dependency>
```

## 4. JWT library — replace monolithic `jjwt` with modular jjwt

```xml
<!-- Before -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt</artifactId>
    <version>0.9.1</version>
</dependency>

<!-- After -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-api</artifactId>
    <version>0.12.3</version>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-impl</artifactId>
    <version>0.12.3</version>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-jackson</artifactId>
    <version>0.12.3</version>
    <scope>runtime</scope>
</dependency>
```

## 5. OpenRewrite plugin (optional — add when you want pom-pinned plugin config instead of ad-hoc Maven invocation)

```xml
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>5.42.0</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2</recipe>
        </activeRecipes>
    </configuration>
    <dependencies>
        <dependency>
            <groupId>org.openrewrite.recipe</groupId>
            <artifactId>rewrite-spring</artifactId>
            <version>5.21.0</version>
        </dependency>
    </dependencies>
</plugin>
```

Then:
```bash
mvn rewrite:run
```

Or invoke transiently without editing pom.xml — see `scripts/openrewrite_run.sh`.
