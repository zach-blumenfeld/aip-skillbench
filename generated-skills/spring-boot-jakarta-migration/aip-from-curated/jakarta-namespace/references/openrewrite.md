# OpenRewrite — Automated Alternative

OpenRewrite can automate the entire `javax.* → jakarta.*` namespace migration. Use this when the project already has a Maven build and the team is comfortable adding a build plugin; otherwise the sed-based `scripts/migrate_imports.sh` flow is faster to apply and easier to inspect.

## Configure the plugin

Add to the `<plugins>` section of `pom.xml`:

```xml
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>5.42.0</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta</recipe>
        </activeRecipes>
    </configuration>
    <dependencies>
        <dependency>
            <groupId>org.openrewrite.recipe</groupId>
            <artifactId>rewrite-migrate-java</artifactId>
            <version>2.26.0</version>
        </dependency>
    </dependencies>
</plugin>
```

## Run the recipe

```bash
mvn rewrite:run
```

## After running

Even with OpenRewrite, still run `scripts/verify_migration.sh` to confirm no `javax.*` Java EE imports remain and that JPA entities have `jakarta.persistence` imports.
