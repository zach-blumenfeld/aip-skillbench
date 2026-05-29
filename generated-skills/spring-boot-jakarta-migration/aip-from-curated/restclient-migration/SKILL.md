---
name: restclient-migration
description: Migrate RestTemplate to RestClient in Spring Boot 3.2+. Use when replacing deprecated RestTemplate with the modern fluent API, updating HTTP client code, or configuring RestClient beans. Covers GET/POST/DELETE/exchange migrations, per-request status handlers, ParameterizedTypeReference for generic bodies, and RestClient bean configuration with a shared base URL.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Replace RestTemplate call sites with RestClient in a Spring Boot 3.2+ codebase.
  RestClient is the modern fluent, synchronous HTTP client introduced in Spring
  Framework 6.1; RestTemplate still compiles but is in maintenance. Work site by
  site: inventory every usage, classify the idiom (GET / POST / DELETE / exchange
  / error handler), apply the matching fluent replacement, prefer a shared
  configured bean over per-service `RestClient.create()`, and finish on a green
  `mvn clean compile` and `mvn test`.

trigger_when:
  - Replacing RestTemplate with RestClient as part of a Spring Boot 2.x → 3.2+ upgrade.
  - User asks to migrate, modernize, or remove RestTemplate.
  - Adding a new HTTP call site in a Spring Boot 3.2+ module — start on RestClient instead of RestTemplate.
  - Configuring a shared HTTP client bean (base URL, default headers) for outbound calls.
  - Reviewing code that mixes RestTemplate and RestClient and needs consolidation on RestClient.

do_not_use_when:
  - The module is on Spring Boot < 3.2 / Spring Framework < 6.1 — RestClient is not available; finish the framework upgrade first.
  - The call site is reactive / non-blocking. Use WebClient, not RestClient.
  - The task is only about Jakarta namespace migration or other dependency bumps with no HTTP-client changes — leave RestTemplate alone unless explicitly in scope.

scope_and_approval: >
  Read-only on the user's source tree until a transformation is applied. Edits
  are local Java changes plus, optionally, a new `@Configuration` class for the
  shared RestClient bean. No network calls, no dependency manifest changes
  beyond what the Spring Boot 3.2+ upgrade already brought in. The final
  `mvn clean compile` and `mvn test` are the only verification gates; do not
  skip either.

steps:
  - name: inventory-call-sites
    description: Run the inventory script over the source tree to list every RestTemplate reference (import, field, constructor, getForEntity, postForEntity, exchange, delete, error handler) with file:line and a kind label.
    script: scripts/inventory_call_sites.sh
    inputs:
      - name: src-root
        type: string
        description: Path to the Java source root to scan (e.g., `src/main/java`).
    outputs:
      - name: call-sites
        type: list[object]
        description: One row per match — `{file, line, kind, snippet}`. Used as the worklist for the rest of the procedure.

  - name: classify-per-call-site
    description: >
      For each row from `call-sites`, read the surrounding Java to identify the
      idiom — GET returning a generic body, GET returning a concrete class,
      POST with JSON body, exchange with custom headers, DELETE, global
      ResponseErrorHandler, etc. Group sites by idiom so the same transformation
      runs over each group.
    inputs:
      - name: call-sites
        type: list[object]
    outputs:
      - name: classified-sites
        type: list[object]
        description: Each row tagged with the migration pattern that applies (see `references/api-mappings.md`).

  - name: configure-restclient-bean
    description: >
      If two or more services target the same base URL or share default
      headers, create a `@Configuration` class exposing a single `RestClient`
      `@Bean` via `RestClient.builder().baseUrl(...).defaultHeader(...).build()`,
      and have each service inject it via constructor. For a single isolated
      call site, `RestClient.create()` inline is fine. Read
      `references/api-mappings.md` § Bean configuration for the template.
    inputs:
      - name: classified-sites
        type: list[object]
    outputs:
      - name: bean-decision
        type: object
        description: Whether a shared bean was introduced and which services consume it.
    one_of:
      - Shared @Bean RestClient with baseUrl + default headers (preferred when ≥2 services share the target).
      - Per-call-site RestClient.create() (acceptable for a single isolated usage).

  - name: apply-migration-pattern
    description: >
      For each classified site, apply the matching fluent replacement. Load
      `references/api-mappings.md` for the per-method recipes (GET, POST,
      DELETE, exchange, generic vs. concrete body types, URI templating). Use
      `ParameterizedTypeReference` for parameterized targets (`Map<String,
      Object>`, `List<User>`) and `.body(Class)` for plain classes. Prefer
      `.uri("/path/{id}", id)` over string concatenation so Spring encodes
      path variables.
    depends_on:
      - configure-restclient-bean
    inputs:
      - name: classified-sites
        type: list[object]
      - name: bean-decision
        type: object
    outputs:
      - name: migrated-sites
        type: list[object]
        description: One row per site with the replacement code applied.

  - name: add-error-handlers
    description: >
      Where the original code used a `ResponseErrorHandler` or relied on
      `RestClientException`-based try/catch around RestTemplate, attach
      `.onStatus(HttpStatusCode::is4xxClientError, ...)` and `.onStatus(...is5xxServerError, ...)`
      handlers to the new RestClient calls. If the original `catch` swallowed
      the exception and returned a default, preserve that behavior: an
      `onStatus` handler that throws will still trigger the existing `catch`.
    depends_on:
      - apply-migration-pattern
    inputs:
      - name: migrated-sites
        type: list[object]
    outputs:
      - name: error-handled-sites
        type: list[object]

  - name: verify-compile-and-tests
    description: >
      Run `mvn clean compile` then `mvn test` from the module root. Both must
      pass. On a compile failure, the most common causes are a missing
      `import org.springframework.web.client.RestClient;`, an
      `import org.springframework.core.ParameterizedTypeReference;` left out
      after switching from `Map.class` to a generic body, or a leftover
      `HttpEntity<>` reference no longer in scope.
    depends_on:
      - add-error-handlers
    inputs:
      - name: error-handled-sites
        type: list[object]
    outputs:
      - name: verification
        type: object
        description: "Shape: {compile: pass|fail, tests: pass|fail, failures: [...]}."

scenarios:
  - need: GET request returning a generic body, currently via `restTemplate.getForEntity(url, Map.class)`.
    context: Inventory tagged the line as `getForEntity`. Target type is `Map<String, Object>`, so `Map.class` was already lossy.
    action: |
      Replace with
      `restClient.get().uri("/users/{id}", userId).retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() {});`.
      Use URI templating, not string concatenation. Drop the `ResponseEntity` /
      `.getBody()` dance.
    outcome: Single fluent call; generics preserved; URL params encoded.

  - need: POST a JSON body and ignore the response, currently via `HttpEntity` + `postForEntity(url, request, Void.class)`.
    context: Inventory tagged it `postForEntity`; the original built `HttpHeaders` manually for `Content-Type` and `Accept`.
    action: |
      `restClient.post().uri("/notifications").contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON).body(payload).retrieve().toBodilessEntity();`
    outcome: No `HttpEntity` wrapper, no manual `HttpHeaders` map; `.toBodilessEntity()` replaces `Void.class` on the response side.

  - need: GET with custom headers, currently via `restTemplate.exchange(url, HttpMethod.GET, new HttpEntity<>(headers), Map.class)`.
    context: Inventory tagged it `exchange`. Custom `Accept` header was the only reason `exchange` was used.
    action: |
      `restClient.get().uri("/users/{id}/profile", userId).accept(MediaType.APPLICATION_JSON).retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() {});`
    outcome: Per-request headers chain directly; no `HttpEntity`, no `HttpMethod` enum.

  - need: Fire-and-forget DELETE, currently `restTemplate.delete(url)` inside a try/catch returning a boolean.
    context: Inventory tagged it `delete`. The existing try/catch must keep working unchanged.
    action: |
      Inside the same try/catch, `restClient.delete().uri("/users/{id}/data", userId).retrieve().toBodilessEntity();`.
      The `.retrieve().toBodilessEntity()` tail is required — without it the request never fires.
    outcome: Boolean control flow unchanged; failures still hit the `catch`.

  - need: Centralize error handling across multiple services that all hit the same external API.
    context: Inventory surfaced a global `ResponseErrorHandler` plus several RestTemplate fields each constructed via `new RestTemplate()`.
    action: |
      Introduce a `@Configuration RestClientConfig` with a `@Bean RestClient`
      built via `RestClient.builder().baseUrl(${external.api.base-url}).defaultHeader(...).build()`.
      Inject it into each service via constructor. Attach per-request `.onStatus(...)` handlers
      where the original `ResponseErrorHandler` differentiated 4xx vs 5xx.
    outcome: One configured bean, services use relative URIs, status handling is explicit at each call site.

  - need: Full `ExternalApiService.verifyEmail(...)` migration end-to-end.
    context: Service originally used `restTemplate.getForEntity(baseUrl + "/verify/email?email=" + email, Map.class)` inside a try/catch that returned false on any exception.
    action: |
      Replace the body with
      `Map<String, Object> response = restClient.get().uri(baseUrl + "/verify/email?email={email}", email).retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() {});`
      and `return response != null && Boolean.TRUE.equals(response.get("valid"));`.
      Keep the try/catch — RestClient still throws on 4xx/5xx by default.
    outcome: Behavior preserved, generics tightened, URL params encoded.

anti_patterns:
  - Concatenating path variables into the URI (`.uri("/users/" + id)`) instead of using URI templates (`.uri("/users/{id}", id)`); breaks Spring's automatic encoding.
  - Replacing `Map.class` with `Map.class` again on the new API — generic bodies need `new ParameterizedTypeReference<Map<String, Object>>() {}`.
  - Forgetting the trailing `.retrieve().toBodilessEntity()` on `delete()` / `post()` calls — the request never fires.
  - Leaving the old `ResponseErrorHandler` registered on a RestTemplate instance that is also being removed; orphaned config compiles but does nothing.
  - Constructing a fresh `RestClient.create()` in every service when two or more share a base URL — drop in a `@Bean` once.
  - Migrating reactive call sites to `RestClient`. RestClient is synchronous; use WebClient for reactive code.
  - Skipping `mvn test` after the migration. The 4xx/5xx default-throw behavior is unchanged but the surrounding code paths usually have assertions that catch regressions.
```
