# Multi-Module Maven Builds

## Reactor options

```bash
# Build all modules
mvn install

# Build a specific module AND its upstream dependencies
mvn install -pl module-name -am

# Build a specific module AND its downstream dependents
mvn install -pl module-name -amd

# Resume from a specific module after a failure mid-reactor
mvn install -rf :module-name

# Parallel — fixed thread count
mvn install -T 4

# Parallel — one thread per CPU core
mvn install -T 1C
```

## When to use which reactor flag

| Goal | Flag |
| ---- | ---- |
| Build only one module — fast iteration on it | `-pl module` |
| Build one module AND every module it depends on (most common when its upstream sibling changed) | `-pl module -am` |
| Build one module AND every module that depends on it (most common when you changed a shared lib and want to know what breaks) | `-pl module -amd` |
| Pick up where a previous failed reactor left off | `-rf :module` |

## Module order in the parent POM

```xml
<modules>
    <module>common</module>
    <module>api</module>
    <module>service</module>
    <module>web</module>
</modules>
```

Maven reorders modules based on inter-module `<dependency>` edges. The
order in `<modules>` is the default — the dependency graph wins on
conflict. `mvn help:effective-pom -pl module` shows the resolved order.
