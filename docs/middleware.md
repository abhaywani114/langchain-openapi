# Production Middleware Pipeline

`langchain_openapi` provides an onion-style middleware architecture for cross-cutting production concerns.

---

## Overview

Middleware components wrap the HTTP execution engine in sequential order:

```text
Request ──► Middleware 1 ──► Middleware 2 ──► Transport Call ──► API
                                                                  │
Response ◄── Middleware 1 ◄── Middleware 2 ◄──────────────────────┘
```

---

## Built-in Middleware

### 1. Retry Middleware

Handles network transport exceptions and transient HTTP error status codes (429, 500, 502, 503, 504) with configurable backoff strategies.

```python
from langchain_openapi_tools import OpenAPIToolkit, RetryMiddleware

retry_mw = RetryMiddleware(
    retries=3,
    backoff="exponential",  # or "fixed"
    backoff_factor=0.5,
    retry_status_codes=(429, 500, 502, 503, 504),
)

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    middleware=[retry_mw],
)
```

### 2. Rate Limit Middleware

Enforces global request rate limits across all tools using a token bucket algorithm.

```python
from langchain_openapi_tools import OpenAPIToolkit, RateLimitMiddleware

rate_mw = RateLimitMiddleware(requests_per_second=10.0)

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    middleware=[rate_mw],
)
```

### 3. Cache Middleware

Caches `GET` response payloads with TTL expiration.

```python
from langchain_openapi_tools import (
    CacheMiddleware,
    InMemoryCacheBackend,
    OpenAPIToolkit,
)

cache_mw = CacheMiddleware(
    ttl=300.0,
    backend=InMemoryCacheBackend(),
    cache_authenticated=False,
)

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    middleware=[cache_mw],
)
```

### 4. Pagination Middleware

Automatically aggregates multi-page API responses when a tool is invoked with `__paginate__=True`.

```python
from langchain_openapi_tools import OpenAPIToolkit, PaginationMiddleware

pag_mw = PaginationMiddleware(max_pages=5, max_items=500)

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    middleware=[pag_mw],
)

# Tool execution with pagination enabled
# await tool.ainvoke({"query": "search_term", "__paginate__": True})
```

### 5. Logging Middleware

Logs outgoing request URLs and incoming response status codes with automatic sensitive header/credential redaction.

```python
from langchain_openapi_tools import LoggingMiddleware, OpenAPIToolkit

log_mw = LoggingMiddleware()

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    middleware=[log_mw],
)
```
