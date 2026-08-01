# Architecture & Core Pipeline

`langchain-openapi` processes raw OpenAPI specs into native LangChain tools using a clean, modular pipeline.

---

## Execution Pipeline

```text
OpenAPI Spec (JSON / YAML / Dict)
              │
              ▼
       OpenAPILoader
              │
              ▼
        OpenAPIParser
              │
              ▼
      SchemaConverter ────► Pydantic Dynamic Models
              │
              ▼
    LangChainToolFactory
              │
              ▼
      AsyncHTTPExecutor
              │
              ▼
     Middleware Pipeline (Retry, Cache, RateLimit, Logging, Pagination)
              │
              ▼
      Request Providers (Authentication & Header Mutations)
              │
              ▼
         httpx.AsyncClient (Target HTTP API)
```

---

## Pipeline Components

### 1. OpenAPILoader
In-gests raw JSON/YAML specifications from local disk files, remote HTTP endpoints, or in-memory dictionaries. Normalizes encoding and format.

### 2. OpenAPIParser
Translates raw specification dictionaries into strongly-typed internal data models (`Operation`, `Parameter`, `RequestBody`, `Response`, `Schema`). Resolves internal `$ref` pointers using `ReferenceResolver`.

### 3. SchemaConverter & PydanticFactory
Converts JSON Schema representations into dynamic Pydantic models at runtime using `pydantic.create_model()`. Ensures incoming LLM function call arguments adhere to strict type schemas.

### 4. LangChainToolFactory
Translates parsed `Operation` models into executable LangChain `StructuredTool` instances.

### 5. AsyncHTTPExecutor
Orchestrates request building, middleware execution, provider transformations, and asynchronous network transport.

### 6. Middleware Pipeline
Intercepts outgoing requests and incoming responses to apply retries, rate limiting, caching, result aggregation, and sanitized telemetry.

### 7. Request Providers
Applies authentication schemes (Bearer tokens, API Keys, Basic Auth) and static headers before network transport.
