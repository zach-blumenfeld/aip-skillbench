# Maven Lifecycle Phases and Goals

## Default Lifecycle — complete phase order

```
1.  validate              - Validate project structure
2.  initialize            - Initialize build state
3.  generate-sources
4.  process-sources
5.  generate-resources
6.  process-resources     - Copy resources to output
7.  compile               - Compile source code
8.  process-classes
9.  generate-test-sources
10. process-test-sources
11. generate-test-resources
12. process-test-resources
13. test-compile          - Compile test sources
14. process-test-classes
15. test                  - Run unit tests
16. prepare-package
17. package               - Create JAR/WAR
18. pre-integration-test
19. integration-test      - Run integration tests
20. post-integration-test
21. verify                - Run verification checks
22. install               - Install to local repo
23. deploy                - Deploy to remote repo
```

Running a phase runs every earlier phase first.

### Common phase commands

```bash
# Compile only
mvn compile

# Compile and run tests
mvn test

# Create package
mvn package

# Install to local repository
mvn install

# Deploy to remote repository
mvn deploy

# Clean and build
mvn clean install

# Skip tests
mvn install -DskipTests

# Skip test compilation AND execution
mvn install -Dmaven.test.skip=true
```

## Clean Lifecycle

```
1. pre-clean
2. clean         - Delete target directory
3. post-clean
```

```bash
mvn clean
mvn clean -DbuildDirectory=out
```

## Site Lifecycle

```
1. pre-site
2. site          - Generate documentation
3. post-site
4. site-deploy   - Deploy documentation
```

```bash
mvn site
mvn site-deploy
```

## Goals vs phases

### Executing phases
```bash
mvn package           # runs all phases up to and including package
```

### Executing goals directly
```bash
mvn compiler:compile
mvn surefire:test
mvn jar:jar

mvn dependency:tree compiler:compile   # multiple goals
```

### Phase-to-goal bindings in pom.xml

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.12.1</version>
            <executions>
                <execution>
                    <id>compile-sources</id>
                    <phase>compile</phase>
                    <goals>
                        <goal>compile</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```
