# Repository configuration

Most missing-artifact failures resolve themselves once Maven Central is
reachable. Check repository configuration only after confirming the
coordinates and the offline cache.

## Maven Central (default)

```xml
<repositories>
    <repository>
        <id>central</id>
        <url>https://repo.maven.apache.org/maven2</url>
    </repository>
</repositories>
```

Central is implicit — declaring it is only needed when an organization
pom has overridden the defaults.

## Private repository

```xml
<repositories>
    <repository>
        <id>company-repo</id>
        <url>https://nexus.company.com/repository/maven-public</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
        </snapshots>
    </repository>
</repositories>
```

## Credentials in `~/.m2/settings.xml`

```xml
<settings>
    <servers>
        <server>
            <id>company-repo</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_PASS}</password>
        </server>
    </servers>
</settings>
```

`<server><id>` must match `<repository><id>` exactly. Never commit
secrets in pom.xml — keep them in `settings.xml` or pulled from env vars.

## Forcing a refresh of cached metadata

```bash
mvn -U clean install         # update snapshots and check for newer releases
mvn dependency:purge-local-repository   # nuclear option: re-download everything
```
