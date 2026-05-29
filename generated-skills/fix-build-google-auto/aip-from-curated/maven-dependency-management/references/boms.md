# BOM (Bill of Materials) imports

A BOM is a `pom`-packaging artifact whose `<dependencyManagement>` block
pins a coherent set of versions. Import one via `scope=import, type=pom`
under your own `<dependencyManagement>`.

## Why prefer a BOM

- One version bump updates an entire dependency family at once.
- Internal version skew is impossible inside a BOM-managed family.
- Project pom omits `<version>` on every artifact the BOM manages — the
  diff after an upgrade is just the BOM bump itself.

## Common BOMs

| Family                     | BOM coordinates                                                |
|----------------------------|----------------------------------------------------------------|
| Spring Boot                | `org.springframework.boot:spring-boot-dependencies`            |
| Spring Cloud               | `org.springframework.cloud:spring-cloud-dependencies`          |
| Jackson                    | `com.fasterxml.jackson:jackson-bom`                            |
| JUnit 5                    | `org.junit:junit-bom`                                          |
| AWS SDK v2                 | `software.amazon.awssdk:bom`                                   |
| Google Cloud Libraries     | `com.google.cloud:libraries-bom`                               |
| Netty                      | `io.netty:netty-bom`                                           |
| gRPC                       | `io.grpc:grpc-bom`                                             |

## Importing a BOM

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>2.23.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- Version omitted: it comes from the BOM. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

## Multiple BOMs and conflicts

When two imported BOMs manage the *same* artifact, the BOM listed **first**
in your `<dependencyManagement>` wins. Order matters. If a downstream BOM
must override an upstream one, declare the override version explicitly
above the BOMs, since explicit `<dependencyManagement>` entries beat
imported ones.
