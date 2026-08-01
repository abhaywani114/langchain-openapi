# Authentication & Request Providers

`langchain-openapi` uses a pluggable `RequestProvider` interface to handle authentication and arbitrary request mutations before requests are sent to target APIs.

---

## Built-in Authentication Providers

### 1. Bearer Auth Provider

Injects an `Authorization: Bearer <TOKEN>` header.

```python
from langchain_openapi import BearerAuthProvider, OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url(
    "https://api.github.com/openapi",
    provider=BearerAuthProvider(token="ghp_secret_token"),
)
```

### 2. API Key Header Provider

Injects an API key in a designated request header.

```python
from langchain_openapi import APIKeyHeaderProvider, OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    provider=APIKeyHeaderProvider(key="secret_key_123", header="X-API-Key"),
)
```

### 3. API Key Query Provider

Appends an API key as a query parameter.

```python
from langchain_openapi import APIKeyQueryProvider, OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    provider=APIKeyQueryProvider(key="secret_key_123", parameter="api_key"),
)
```

### 4. Basic Auth Provider

Injects HTTP Basic Authentication credentials.

```python
from langchain_openapi import BasicAuthProvider, OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    provider=BasicAuthProvider(username="admin", password="password123"),
)
```

---

## Combining Providers with CompositeProvider

Chain multiple request providers sequentially using `CompositeProvider`:

```python
from langchain_openapi import (
    BearerAuthProvider,
    CompositeProvider,
    CookiesProvider,
    OpenAPIToolkit,
    StaticHeadersProvider,
)

composite = CompositeProvider(
    [
        BearerAuthProvider(token="jwt_token_here"),
        StaticHeadersProvider({"User-Agent": "langchain-openapi/1.0"}),
        CookiesProvider({"session_id": "sess_999"}),
    ]
)

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    provider=composite,
)
```
