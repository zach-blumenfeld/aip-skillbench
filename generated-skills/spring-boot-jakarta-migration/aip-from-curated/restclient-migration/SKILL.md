---
name: restclient-migration
description: Migrate RestTemplate to RestClient in Spring Boot 3.2+. Use when replacing deprecated RestTemplate with modern fluent API, updating HTTP client code, or configuring RestClient beans. Covers GET/POST/DELETE migrations, error handling, and ParameterizedTypeReference usage.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Migrate Spring Boot RestTemplate code to RestClient (Spring Framework 6.1 /
  Spring Boot 3.2+). Covers GET, POST, DELETE, and exchange call shapes;
  ParameterizedTypeReference for generic response bodies; status-handler error
  mapping; and the bean configuration shift from constructor-injected templates
  to the builder pattern.

trigger_when:
  - User asks to replace deprecated RestTemplate with RestClient.
  - Migrating a Spring Boot 3.2+ codebase off RestTemplate.
  - A class uses RestTemplate.getForEntity / postForEntity / exchange / delete.
  - Configuring a new HTTP client bean in a Spring Boot 3.2+ project.
  - User mentions modern HTTP client, fluent HTTP API, or RestTemplate deprecation.

do_not_use_when:
  - Project is reactive (Spring WebFlux) — use WebClient, not RestClient.
  - Project targets Spring Boot < 3.2 (RestClient is unavailable before Spring Framework 6.1).

steps:
  - name: load-migration-patterns
    description: >
      Read references/migration-patterns.md before editing any code. It is the
      source of truth for every supported call shape (GET, POST, exchange,
      DELETE), bean configuration, error handling, and ParameterizedTypeReference
      usage. Do not improvise translations.
    outputs:
      - name: patterns-loaded
        type: boolean

  - name: inventory-resttemplate-touchpoints
    description: >
      Find every RestTemplate touchpoint in the target code — field
      declarations, instantiations (`new RestTemplate()`), constructor / setter
      injections, and call sites (`getForEntity`, `postForEntity`, `exchange`,
      `delete`, `getForObject`, `postForObject`, etc.). Record file, line,
      method, and call shape for each.
    inputs:
      - name: patterns-loaded
        type: boolean
    outputs:
      - name: call-sites
        type: list[object]
        description: One entry per touchpoint — file, line, method, call shape.

  - name: rewrite-call-sites
    description: >
      For each call site, apply the matching pattern from
      references/migration-patterns.md. Defaults to follow without exception —
      (a) URI template variables (`uri("/path/{id}", id)`), never string
      concatenation of user input; (b) `ParameterizedTypeReference` for generic
      body types (`Map<...>`, `List<...>`), class literal otherwise; (c)
      `.retrieve().toBodilessEntity()` when the response body is unused; (d)
      do not translate `exchange(...)` literally — use the higher-level
      `.get()` / `.post()` chain when it covers the call.
    inputs:
      - name: call-sites
        type: list[object]
    outputs:
      - name: rewritten-call-sites
        type: list[object]

  - name: replace-instantiation-or-introduce-bean
    description: >
      Replace `new RestTemplate()` with either `RestClient.create()` (no shared
      base URL or headers) or a constructor-injected `RestClient` bean. If
      multiple call sites share a base URL or default headers, add a
      `@Configuration` class with a `@Bean RestClient` built via
      `RestClient.builder().baseUrl(...).defaultHeader(...).build()` — see
      references/migration-patterns.md § 5. Do not leave `new RestTemplate()`
      in any constructor once a `RestClient` bean exists.
    inputs:
      - name: rewritten-call-sites
        type: list[object]
    outputs:
      - name: bean-changes
        type: list[string]

  - name: migrate-error-handling
    description: >
      Where the original code used a `ResponseErrorHandler`, replace it with
      chained `.onStatus(HttpStatusCode::is4xxClientError, (req, res) -> { ... })`
      and `.onStatus(HttpStatusCode::is5xxServerError, ...)` calls placed before
      `.body(...)`. Throw typed exceptions inside the handlers — do not return
      sentinel values. Pre-existing try/catch blocks that already swallow
      errors around individual calls stay in place.
    inputs:
      - name: rewritten-call-sites
        type: list[object]
    outputs:
      - name: error-handling-changes
        type: list[string]

  - name: verify
    description: >
      Compile the project and run tests (`./mvnw test`, `./gradlew test`, or
      the project's equivalent). Confirm no `org.springframework.web.client.RestTemplate`
      import remains except where the call shape genuinely is not migrating
      this round. Resolve any compile errors using references/migration-patterns.md.
    outputs:
      - name: verification-passed
        type: boolean

scenarios:
  - need: A service method does `restTemplate.getForEntity(url, Map.class)` and returns the body.
    action: >
      Rewrite as `restClient.get().uri(template, args).retrieve().body(new
      ParameterizedTypeReference<Map<String, Object>>() {})`. Move any path
      variables out of the concatenated URL and into the URI template.
    outcome: Generic type info preserved; URI-encoded path variables.

  - need: A service has `private final RestTemplate restTemplate = new RestTemplate();` plus several methods sharing a baseUrl and JSON content type.
    action: >
      Add a `@Configuration` class with a `@Bean RestClient` built from
      `RestClient.builder().baseUrl(baseUrl).defaultHeader(CONTENT_TYPE, APPLICATION_JSON_VALUE).build()`.
      Constructor-inject it. Call sites use relative paths.
    outcome: One source of HTTP configuration; methods read more cleanly.

  - need: Previous code registered a `ResponseErrorHandler` bean that mapped 4xx to UserNotFoundException and 5xx to ExternalServiceException.
    action: >
      Delete the handler registration. Add chained `.onStatus(HttpStatusCode::is4xxClientError, ...)`
      and `.onStatus(HttpStatusCode::is5xxServerError, ...)` before `.body(...)` on each call site
      that needs the mapping.
    outcome: Error mapping lives next to the call; no global handler bean needed.

  - need: A reactive (Spring WebFlux) service uses `RestTemplate` internally.
    action: >
      Stop. RestClient is the wrong target for reactive code — migrate to
      `WebClient` (`.bodyToMono(...)`, `.bodyToFlux(...)`) instead.
    outcome: Reactive call signatures preserved; no blocking inside the reactive chain.

anti_patterns:
  - Using raw `Map` or `List` as the body type — pass a `ParameterizedTypeReference` so generic type info survives type erasure.
  - Concatenating user-supplied values into the `uri(...)` string instead of passing them as URI template variables.
  - Leaving `new RestTemplate()` in a constructor while a `@Bean RestClient` is configured elsewhere in the project.
  - Translating `exchange(...)` literally to `RestClient.method(HttpMethod.GET, ...)` when the higher-level `.get()` / `.post()` form covers the call.
  - Using RestClient in a reactive/WebFlux codebase — that is WebClient's territory.
  - Wrapping a whole call in `try/catch` when `.onStatus(...)` would express the intent cleanly per status family.
  - Forgetting `.retrieve().toBodilessEntity()` on POST/DELETE calls whose response body is unused — the request will be silently deferred.
```
