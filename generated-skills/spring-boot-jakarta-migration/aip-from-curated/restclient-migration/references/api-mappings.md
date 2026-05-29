# RestTemplate → RestClient API mappings

Load when applying a migration to a specific call site. Each row pairs the legacy
`RestTemplate` idiom with the `RestClient` replacement and the gotchas.

## Surface comparison

| Concern             | RestTemplate                        | RestClient                                          |
|---------------------|-------------------------------------|-----------------------------------------------------|
| API style           | Template methods                    | Fluent builder                                      |
| Construction        | `new RestTemplate()`                | `RestClient.create()` or `RestClient.builder()…build()` |
| Configuration       | Constructor / setters               | Builder pattern                                     |
| Error handling      | `ResponseErrorHandler` (global)     | `.onStatus(predicate, handler)` (per-request)       |
| Generic types       | `Map.class` / `new ParameterizedTypeReference<>(){}` on `exchange` | `.body(new ParameterizedTypeReference<>(){})`       |
| URI templating      | `restTemplate.getForEntity(url, T.class, vars)` | `.uri("/path/{id}", id)`                            |

## Per-method mappings

### GET that returns a generic body (`Map`, `List<T>`, ...)

```java
// Before
ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
return response.getBody();

// After
return restClient.get()
    .uri("/users/{id}", userId)                                 // URI templating, not string concat
    .retrieve()
    .body(new ParameterizedTypeReference<Map<String, Object>>() {});
```

Use `ParameterizedTypeReference` whenever the target type is parameterized
(`Map<String, Object>`, `List<User>`). For a plain class, use `.body(User.class)`.

### GET that returns a single concrete class

```java
// Before
User user = restTemplate.getForObject("/users/" + id, User.class);

// After
User user = restClient.get()
    .uri("/users/{id}", id)
    .retrieve()
    .body(User.class);
```

### POST with a JSON body, response ignored

```java
// Before
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
HttpEntity<Map<String, String>> request = new HttpEntity<>(payload, headers);
restTemplate.postForEntity(url, request, Void.class);

// After
restClient.post()
    .uri("/notifications")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .body(payload)
    .retrieve()
    .toBodilessEntity();
```

`.toBodilessEntity()` replaces `Void.class` on the response side.

### exchange(HttpMethod.GET, ..., headers, T) for custom headers

```java
// Before
HttpHeaders headers = new HttpHeaders();
headers.setAccept(Collections.singletonList(MediaType.APPLICATION_JSON));
HttpEntity<?> request = new HttpEntity<>(headers);
ResponseEntity<Map> response = restTemplate.exchange(url, HttpMethod.GET, request, Map.class);

// After
restClient.get()
    .uri("/users/{id}/profile", userId)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(new ParameterizedTypeReference<Map<String, Object>>() {});
```

Per-request headers move to chained methods (`.accept(...)`, `.header(...)`,
`.contentType(...)`). No `HttpEntity` wrapper, no `HttpMethod` enum.

### DELETE

```java
// Before
restTemplate.delete(baseUrl + "/users/" + id + "/data");

// After
restClient.delete()
    .uri("/users/{id}/data", id)
    .retrieve()
    .toBodilessEntity();
```

### Status-code error handling

```java
// Before — global ResponseErrorHandler
restTemplate.setErrorHandler(new ResponseErrorHandler() { ... });

// After — per-request status handlers
restClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .onStatus(HttpStatusCode::is4xxClientError, (request, response) -> {
        throw new UserNotFoundException("User not found: " + userId);
    })
    .onStatus(HttpStatusCode::is5xxServerError, (request, response) -> {
        throw new ExternalServiceException("External service error");
    })
    .body(new ParameterizedTypeReference<Map<String, Object>>() {});
```

A global `RestClient.builder().defaultStatusHandler(...)` works too, but the
per-request form maps more cleanly from existing `try { ... } catch (...)` sites.

## Bean configuration

When several services share a base URL or default headers, configure a single
`RestClient` bean instead of `RestClient.create()` per service.

```java
@Configuration
public class RestClientConfig {

    @Value("${external.api.base-url}")
    private String baseUrl;

    @Bean
    public RestClient restClient() {
        return RestClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
            .build();
    }
}
```

Services then inject `RestClient` via constructor and use relative URIs:

```java
@Service
public class ExternalApiService {
    private final RestClient restClient;

    public ExternalApiService(RestClient restClient) {
        this.restClient = restClient;
    }

    public Map<String, Object> getUser(String userId) {
        return restClient.get()
            .uri("/users/{id}", userId)
            .retrieve()
            .body(new ParameterizedTypeReference<Map<String, Object>>() {});
    }
}
```

## When NOT to use RestClient

For reactive / non-blocking call sites, `WebClient` is the right replacement, not
`RestClient`:

```java
WebClient webClient = WebClient.create(baseUrl);
Mono<User> userMono = webClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .bodyToMono(User.class);
```

`RestClient` is for synchronous (blocking) call sites in non-reactive
applications.

## Gotchas

- `RestClient` requires Spring Framework 6.1 / Spring Boot 3.2+. If the module
  hasn't finished upgrading, the type won't resolve.
- `restTemplate.getForEntity(...).getBody()` returned a raw `Map`. The fluent
  equivalent should use `ParameterizedTypeReference<Map<String, Object>>` —
  switching to `Map.class` silently drops generics and breaks downstream
  `.get("valid")` style access on some Spring versions.
- Migrating a `try { ... } catch (RestClientException e) { return false; }` block
  to RestClient: a 4xx/5xx still throws by default after `.retrieve()`, so the
  `catch` continues to fire. If you add `.onStatus(...)`, the handler runs
  *before* the throw — make sure the handler still throws, or behavior changes.
- `restTemplate.delete(url)` returned `void`. The RestClient form must end in
  `.retrieve().toBodilessEntity()` (or `.toBodilessEntity()` is consumed) —
  otherwise the request is never sent.
- String concatenation in `.uri("/path/" + id)` works but defeats URI-template
  encoding. Prefer `.uri("/path/{id}", id)` so Spring encodes path variables.
