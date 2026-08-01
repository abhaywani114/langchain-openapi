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
      Spec Adapter Layer  (Swagger 2.0 → 3.0 normalization; 3.0/3.1 pass-through)
              │
              ▼
        OpenAPIParser
              │
              ▼
      SchemaConverter ────► Pydantic Dynamic Models
              │              (oneOf/anyOf → Union, allOf → merged model,
              │               const → Literal, nullable → Optional)
              ▼
    LangChainToolFactory
              │
              ▼
      AsyncHTTPExecutor
              │
              ▼
     Media-type dispatch (application/json, x-www-form-urlencoded,
                          multipart/form-data, text/*, application/xml,
                          vendor +json variants)
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

### Alternate LangChain Interface: Generic HTTP Toolkit

Everything above the `LangChainToolFactory` node is shared with the
[`GenericOpenAPIToolkit`][langchain_openapi_tools.generic_toolkit.GenericOpenAPIToolkit],
which swaps the *one-tool-per-operation* strategy for a constant set of
tools plus discovery helpers:

```text
            OpenAPISpec (shared)
                   │
                   ▼
              OpenAPIParser
                   │
         ┌───────┴───────────────┐
         ▼                        ▼
 LangChainToolFactory       OperationIndex
 (typed per-op)              (keyword + fuzzy)
         │                        │
         │                        ▼
         │            GenericHTTPToolFactory
         │            (GET/POST/PUT/PATCH/DELETE +
         │             search_operations, describe_operation,
         │             list_operations, list_tags)
         └──────┬────────────────┘
                ▼
     AsyncHTTPExecutor.execute() / .request()
                (shared provider + middleware + client)
```

The generic tools invoke
`AsyncHTTPExecutor.request(method, endpoint, ...)`, a public raw-request
entry point that reuses the same middleware pipeline, request providers,
timeout, and HTTP client as the typed `execute(operation, arguments)`
call. See the [Generic & Hybrid Toolkits guide](generic_toolkit.md).

---

## Pipeline Components

### 1. OpenAPILoader
In-gests raw JSON/YAML specifications from local disk files, remote HTTP endpoints, or in-memory dictionaries. Normalizes encoding and format. When loading from a URL, the loader retains the source URL on the resulting `OpenAPISpec` so relative `servers` entries (OpenAPI 3.x) and missing `host` values (Swagger 2.0) can be resolved to absolute request URLs downstream.

### 2. Spec Adapter Layer
`langchain_openapi_tools.adapters` provides `SpecAdapter` implementations for every supported family: `Swagger2Adapter` normalizes Swagger 2.0 documents into OpenAPI 3.0 shape (using the source URL to fill in a missing `host`), and `OpenAPI3Adapter` accepts both 3.0.x and 3.1.x without modification. `detect_spec_version()`, `select_adapter()`, and `normalize_spec()` provide the public entry points. The resulting family tag is preserved on `OpenAPISpec.spec_family`.

### 3. OpenAPIParser
Translates raw specification dictionaries into strongly-typed internal data models (`Operation`, `Parameter`, `RequestBody`, `Response`, `Schema`). Resolves internal `$ref` pointers using `ReferenceResolver`, and extracts polymorphic keywords (`oneOf`, `anyOf`, `allOf`), `const` values, and `readOnly`/`writeOnly`/`deprecated` markers.

### 4. SchemaConverter & PydanticFactory
Converts JSON Schema representations into dynamic Pydantic models at runtime using `pydantic.create_model()`. Union keywords become `typing.Union`s, `allOf` merges into a single model, list-form `type` becomes a `Union` of Python types, and `nullable` / `type: [X, "null"]` become `Optional[X]`. Incoming LLM tool arguments are validated against the resulting schema before dispatch.

### 5. LangChainToolFactory
Translates parsed `Operation` models into executable LangChain `StructuredTool` instances.

### 6. AsyncHTTPExecutor
Orchestrates request building, middleware execution, provider transformations, and asynchronous network transport. `RequestBuilder` inspects the operation's request-body content-types and dispatches to the correct httpx encoding (JSON, form-urlencoded, multipart with files, or raw text/XML), and coerces validated Pydantic body models back to JSON-safe primitives before serialization.

### 7. Middleware Pipeline
Intercepts outgoing requests and incoming responses to apply retries, rate limiting, caching, result aggregation, and sanitized telemetry.

### 8. Request Providers
Applies authentication schemes (Bearer tokens, API Keys, Basic Auth) and static headers before network transport.

### 9. OperationIndex & GenericHTTPToolFactory
[`OperationIndex`][langchain_openapi_tools.search.OperationIndex] builds
an in-memory searchable projection of every parsed `Operation` (keyword,
fuzzy, and tag/method filtering — no external vector database).
[`GenericHTTPToolFactory`][langchain_openapi_tools.generic_toolkit.GenericHTTPToolFactory]
uses the index to expose four LangChain discovery tools
(`search_operations`, `describe_operation`, `list_operations`,
`list_tags`) alongside the five generic HTTP tools
(`GET`/`POST`/`PUT`/`PATCH`/`DELETE`). All of these share the same
`AsyncHTTPExecutor` via its `request()` method — so authentication,
retry, rate-limit, cache, and pagination middleware are inherited
without duplicated logic. See the
[Generic & Hybrid Toolkits guide](generic_toolkit.md).
