# RestTemplate → RestClient migration patterns

Source of truth for translating each RestTemplate call shape to RestClient (Spring Framework 6.1 / Spring Boot 3.2+). Match each call site to one of these patterns and apply the rewrite literally; do not improvise.

## Key API differences

| Feature        | RestTemplate            | RestClient                   |
|----------------|-------------------------|------------------------------|
| API style      | Template methods        | Fluent builder               |
| Configuration  | Constructor injection   | Builder pattern              |
| Error handling | `ResponseErrorHandler`  | Chained `.onStatus(...)`     |
| Generic types  | Limited                 | `ParameterizedTypeReference` |

## 1. GET → body

### Before (RestTemplate)

```java
public Map<String, Object> getUser(String userId) {
    String url = "https://api.example.com/users/" + userId;
    ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
    return response.getBody();
}
```

### After (RestClient)

```java
public Map<String, Object> getUser(String userId) {
    return restClient.get()
        .uri("https://api.example.com/users/{id}", userId)
        .retrieve()
        .body(new ParameterizedTypeReference<Map<String, Object>>() {});
}
```

Notes:
- Replace string concatenation with the `uri(template, args...)` form so path variables are URI-encoded.
- For generic body types (`Map<...>`, `List<...>`), use `ParameterizedTypeReference` — using raw `Map.class` loses generic type info.

## 2. POST with JSON body

### Before

```java
public void sendNotification(String userId, String message) {
    String url = baseUrl + "/notifications";
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.setAccept(Collections.singletonList(MediaType.APPLICATION_JSON));
    Map<String, String> payload = Map.of("userId", userId, "message", message);
    HttpEntity<Map<String, String>> request = new HttpEntity<>(payload, headers);
    restTemplate.postForEntity(url, request, Void.class);
}
```

### After

```java
public void sendNotification(String userId, String message) {
    Map<String, String> payload = Map.of("userId", userId, "message", message);
    restClient.post()
        .uri(baseUrl + "/notifications")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(payload)
        .retrieve()
        .toBodilessEntity();
}
```

Notes:
- `HttpHeaders` + `HttpEntity` plumbing collapses into chained `.contentType(...)`, `.accept(...)`, and `.body(payload)` calls.
- When the caller doesn't need the response body, terminate with `.retrieve().toBodilessEntity()`.

## 3. Exchange (GET with custom headers)

### Before

```java
public Map<String, Object> enrichUserProfile(String userId) {
    String url = baseUrl + "/users/" + userId + "/profile";
    HttpHeaders headers = new HttpHeaders();
    headers.setAccept(Collections.singletonList(MediaType.APPLICATION_JSON));
    HttpEntity<?> request = new HttpEntity<>(headers);
    ResponseEntity<Map> response = restTemplate.exchange(url, HttpMethod.GET, request, Map.class);
    return response.getBody();
}
```

### After

```java
public Map<String, Object> enrichUserProfile(String userId) {
    return restClient.get()
        .uri(baseUrl + "/users/{id}/profile", userId)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(new ParameterizedTypeReference<Map<String, Object>>() {});
}
```

Notes:
- `exchange(url, HttpMethod.GET, ...)` collapses to a direct `.get()` chain — do not translate `exchange()` literally when a higher-level method covers the call.

## 4. DELETE

### Before

```java
public boolean requestDataDeletion(String userId) {
    try {
        String url = baseUrl + "/users/" + userId + "/data";
        restTemplate.delete(url);
        return true;
    } catch (Exception e) {
        return false;
    }
}
```

### After

```java
public boolean requestDataDeletion(String userId) {
    try {
        restClient.delete()
            .uri(baseUrl + "/users/{id}/data", userId)
            .retrieve()
            .toBodilessEntity();
        return true;
    } catch (Exception e) {
        return false;
    }
}
```

Notes:
- Existing try/catch blocks that swallow errors and return a boolean/Optional stay in place — they aren't replaced by `.onStatus(...)`.

## 5. RestClient configuration (bean)

Use a `@Configuration` class when the client has a base URL, default headers, or any other shared configuration.

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

Consume it via constructor injection. Methods can then use relative URIs:

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

If the call site needs no shared base URL or headers, `RestClient.create()` inside the constructor is acceptable:

```java
this.restClient = RestClient.create();
```

Do not leave `new RestTemplate()` in any constructor once a `@Bean RestClient` exists in the project — inject the bean instead.

## 6. Error handling — `.onStatus(...)`

Replace `ResponseErrorHandler` registrations with chained `.onStatus(...)` handlers before `.body(...)`:

```java
public Map<String, Object> getUserWithErrorHandling(String userId) {
    return restClient.get()
        .uri("/users/{id}", userId)
        .retrieve()
        .onStatus(HttpStatusCode::is4xxClientError, (request, response) -> {
            throw new UserNotFoundException("User not found: " + userId);
        })
        .onStatus(HttpStatusCode::is5xxServerError, (request, response) -> {
            throw new ExternalServiceException("External service error");
        })
        .body(new ParameterizedTypeReference<Map<String, Object>>() {});
}
```

Each `.onStatus(predicate, handler)` runs before `.body(...)` resolves; throw a typed exception or transform the response inside the handler.

## 7. Type-safe responses

Use `ParameterizedTypeReference` for any body type with generics:

```java
Map<String, Object> map = restClient.get()
    .uri("/data")
    .retrieve()
    .body(new ParameterizedTypeReference<Map<String, Object>>() {});

List<User> users = restClient.get()
    .uri("/users")
    .retrieve()
    .body(new ParameterizedTypeReference<List<User>>() {});
```

Use a class literal for non-generic types:

```java
User user = restClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .body(User.class);

String text = restClient.get()
    .uri("/text")
    .retrieve()
    .body(String.class);
```

## 8. Worked end-to-end migration

### Before

```java
@Service
public class ExternalApiService {
    private final RestTemplate restTemplate;

    @Value("${external.api.base-url}")
    private String baseUrl;

    public ExternalApiService() {
        this.restTemplate = new RestTemplate();
    }

    public boolean verifyEmail(String email) {
        try {
            String url = baseUrl + "/verify/email?email=" + email;
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            return Boolean.TRUE.equals(response.getBody().get("valid"));
        } catch (Exception e) {
            return false;
        }
    }
}
```

### After

```java
@Service
public class ExternalApiService {
    private final RestClient restClient;

    @Value("${external.api.base-url}")
    private String baseUrl;

    public ExternalApiService() {
        this.restClient = RestClient.create();
    }

    public boolean verifyEmail(String email) {
        try {
            Map<String, Object> response = restClient.get()
                .uri(baseUrl + "/verify/email?email={email}", email)
                .retrieve()
                .body(new ParameterizedTypeReference<Map<String, Object>>() {});
            return response != null && Boolean.TRUE.equals(response.get("valid"));
        } catch (Exception e) {
            return false;
        }
    }
}
```

## 9. Reactive escape hatch — `WebClient`

For reactive/WebFlux applications, RestClient is the wrong target. Use `WebClient` instead:

```java
WebClient webClient = WebClient.create(baseUrl);

Mono<User> userMono = webClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .bodyToMono(User.class);
```

`RestClient` is for synchronous operations in non-reactive applications.
