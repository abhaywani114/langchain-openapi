# Generic & Hybrid Toolkits

`langchain-openapi` ships **three execution strategies** for turning an
OpenAPI specification into LangChain tools. They all share the same
loader, parser, reference resolver, request providers, middleware, and
`AsyncHTTPExecutor` — only the LangChain interface changes.

| Toolkit | Best for | Tool count |
| ------- | -------- | ---------- |
| **Typed** — [`OpenAPIToolkit`][langchain_openapi_tools.toolkit.OpenAPIToolkit] | Small & medium APIs, maximum correctness | One per operation |
| **Generic** — [`GenericOpenAPIToolkit`][langchain_openapi_tools.generic_toolkit.GenericOpenAPIToolkit] | Large APIs (GitHub, Kubernetes, Stripe), low context usage | Constant (9 tools) |
| **Hybrid** — `GenericOpenAPIToolkit.get_tools(mode="hybrid")` | Enterprise APIs with hot paths + long tails | Typed for selected ops + generic for the rest |

---

## Why a Generic Toolkit?

Generating one typed tool per operation is ideal for correctness but does
not scale for large surfaces. A modern spec such as the GitHub REST API
declares **hundreds** of operations. Bundling every one into the prompt
causes:

- Very large system prompts and slow agent start-up.
- Context-window exhaustion on smaller models.
- Increased hallucination rate as the tool list grows.

The Generic Toolkit exposes a **fixed** set of five HTTP tools plus four
discovery helpers, regardless of whether the underlying API has ten
endpoints or ten thousand.

---

## Quick Example

```python
from langchain_openapi_tools import GenericOpenAPIToolkit

toolkit = GenericOpenAPIToolkit.from_url(
    "https://petstore3.swagger.io/api/v3/openapi.json"
)

tools = toolkit.get_tools()  # constant set — see next section
```

---

## Generated Tools

`GenericOpenAPIToolkit.get_tools(mode="generic")` returns:

### HTTP Tools

| Tool | Arguments | Purpose |
| ---- | --------- | ------- |
| `GET`    | `endpoint`, `params`, `headers` | HTTP GET request |
| `POST`   | `endpoint`, `body`, `params`, `headers` | HTTP POST request with optional JSON body |
| `PUT`    | `endpoint`, `body`, `params`, `headers` | HTTP PUT request |
| `PATCH`  | `endpoint`, `body`, `params`, `headers` | HTTP PATCH request |
| `DELETE` | `endpoint`, `params`, `headers` | HTTP DELETE request |

`endpoint` may be a path relative to the toolkit's base URL
(`"/pets/1"`) or an absolute URL (`"https://api.example.com/pets/1"`).

### Discovery Tools

| Tool | Arguments | Purpose |
| ---- | --------- | ------- |
| `search_operations` | `query`, `limit`, `tag?`, `method?` | Rank operations by relevance to a query |
| `describe_operation` | `operation_id` | Return summary, description, parameters, request body, responses |
| `list_operations` | `tag?`, `method?`, `limit` | Enumerate operations (optionally filtered) |
| `list_tags` | — | Enumerate every tag declared by the spec |

---

## Intended Reasoning Flow

Instead of dumping the entire OpenAPI document into the system prompt,
the agent discovers endpoints on demand:

```text
User → search_operations("books")
     → describe_operation("get_books")
     → GET(endpoint="/books", params={...})
     → response
```

This keeps prompt size constant *regardless of API size*.

---

## Shared Infrastructure

Every feature that works with the typed toolkit — authentication,
retries, rate limiting, caching, pagination, logging — works with the
generic toolkit **without changing a single line of the middleware or
provider code**. The two toolkits share the same
[`AsyncHTTPExecutor`][langchain_openapi_tools.executor.AsyncHTTPExecutor]
instance.

```python
from langchain_openapi_tools import (
    BearerAuthProvider,
    CacheMiddleware,
    GenericOpenAPIToolkit,
    InMemoryCacheBackend,
    RetryMiddleware,
)

toolkit = GenericOpenAPIToolkit.from_url(
    "https://api.example.com/openapi.json",
    provider=BearerAuthProvider(token="…"),
    middleware=[
        RetryMiddleware(retries=3),
        CacheMiddleware(backend=InMemoryCacheBackend(), ttl=60),
    ],
    timeout=30,
)
```

---

## Hybrid Mode

Combine both worlds. Typed tools are generated for a curated subset of
operations (via `typed_tags` or `typed_operations`); everything else
remains reachable through the generic HTTP tools.

```python
toolkit = GenericOpenAPIToolkit.from_url(url)

tools = toolkit.get_tools(
    mode="hybrid",
    typed_tags=["Books", "Users"],
)
```

`OpenAPIToolkit` also accepts `mode="generic"` / `mode="hybrid"` and
transparently delegates, so existing setups can opt in without switching
classes:

```python
from langchain_openapi_tools import OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url(url)
tools = toolkit.get_tools(mode="hybrid", typed_tags=["Books"])
```

The default (`mode="typed"`) preserves full backward compatibility.

---

## Configuration

Pass a
[`GenericToolkitConfig`][langchain_openapi_tools.generic_toolkit.GenericToolkitConfig]
to customise the generic toolkit:

```python
from langchain_openapi_tools import GenericOpenAPIToolkit, GenericToolkitConfig

config = GenericToolkitConfig(
    include_http_methods=["GET", "POST"],     # limit exposed HTTP tools
    include_discovery_tools=True,             # toggle search/describe/list
    typed_tags=["Books"],                     # default typed tags for hybrid
)

toolkit = GenericOpenAPIToolkit.from_url(url, config=config)
```

---

## Operation Search Index

The discovery tools are backed by
[`OperationIndex`][langchain_openapi_tools.search.OperationIndex], an
in-memory index that supports keyword, fuzzy, and tag/method filtering.
**No external vector database required.**

Available programmatically via the toolkit:

```python
toolkit.list_operations()                       # summary list
toolkit.list_tags()                             # sorted tag set
toolkit.search_operations("payments", limit=5)  # ranked results
toolkit.describe_operation("createPayment")     # full detail
```

Scoring signals combined per candidate:

1. **Substring match** on operationId, summary, and path.
2. **Token overlap** against the entry's haystack.
3. **Fuzzy ratio** via `difflib.SequenceMatcher` as a tiebreaker.

See the [OperationIndex API reference](api/search.md) for details.

---

## When to Use Which Toolkit

- Use the **Typed** toolkit when your API is small enough that all
  operations fit comfortably in the prompt and you want the strictest
  possible per-operation validation.
- Use the **Generic** toolkit for large or rapidly-changing APIs where
  a constant tool surface with on-demand discovery is more important
  than compile-time-shaped schemas.
- Use the **Hybrid** toolkit for enterprise APIs where a few endpoints
  are hot paths that benefit from typed schemas while the long tail can
  be reached generically.
