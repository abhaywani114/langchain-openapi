# langchain-openapi

<p align="center">
  <!-- Logo Placeholder -->
  <img src="docs/assets/logo.png" alt="langchain-openapi logo" width="200" onerror="this.style.display='none'"/>
</p>

<p align="center">
  <em>Convert OpenAPI v3.0 & v3.1 and Swagger 2.0 specifications into native, production-grade LangChain tools.</em>
</p>

<p align="center">
  <a href="https://github.com/abhaywani114/langchain-openapi/actions/workflows/ci.yml"><img src="https://github.com/abhaywani114/langchain-openapi/actions/workflows/ci.yml/badge.svg" alt="CI Status"/></a>
  <a href="https://pypi.org/project/langchain-openapi-tools/"><img src="https://img.shields.io/pypi/v/langchain-openapi-tools.svg" alt="PyPI Version"/></a>
  <a href="https://abhaywani114.github.io/langchain-openapi/"><img src="https://img.shields.io/badge/docs-mkdocs-blue.svg" alt="Documentation"/></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"/></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/code%20style-ruff-000000.svg" alt="Code Style: Ruff"/></a>
  <a href="http://mypy-lang.org/"><img src="https://img.shields.io/badge/mypy-checked-blue.svg" alt="Checked with MyPy"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"/></a>
</p>

---

`langchain_openapi` is a modern Python library designed to seamlessly convert OpenAPI v3.0, v3.1, and Swagger 2.0 specifications into native, type-safe [LangChain](https://github.com/langchain-ai/langchain) tools for AI agents and LLM applications.

No python code generation is required—tools are generated dynamically at runtime with strict Pydantic input schemas, prompt optimization options, and production-ready middleware.

---

## Installation & Importing

Install the PyPI package:

```bash
pip install langchain-openapi-tools
# or using uv
uv add langchain-openapi-tools
```

Import in Python:

```python
from langchain_openapi_tools import OpenAPIToolkit, OpenAPIToolkitConfig
```

### Migration Note

```python
# Old (deprecated, but still works for backward compatibility):
from langchain_openapi import OpenAPIToolkit

# New (recommended):
from langchain_openapi_tools import OpenAPIToolkit
```

---

## Features

- ⚡ **Zero-Code Tool Generation**: Runtime conversion of OpenAPI specs (YAML/JSON) into LangChain `StructuredTool`s.
- 🧭 **Typed, Generic & Hybrid Toolkits**: Choose per-operation typed tools, a constant set of generic `GET`/`POST`/... tools with on-demand endpoint discovery, or a hybrid mix — all sharing the same execution stack.
- 🚀 **Swagger 2.0 & OpenAPI 3.x**: Native normalization of legacy Swagger 2.0 and modern OpenAPI 3.0/3.1 specs.
- 🗜️ **Prompt Optimization & Filtering**: Description modes (`full`, `compact`, `minimal`), description compression, overrides, callbacks, and operation/tag filtering to drastically reduce context window usage.
- 🔒 **Pluggable Authentication**: Built-in support for Bearer Tokens, API Key Headers, Query Parameters, Basic Auth, and custom request providers.
- 🛡️ **Production Middleware**: Composable middleware architecture for Retries (exponential backoff), Rate Limiting (token-bucket), Caching (TTL), Pagination aggregation, and Sanitized Logging.
- 🎯 **Type-Safe Validation**: Dynamically generated Pydantic input schemas ensure LLM arguments adhere strictly to specification types before network transport.
- 🌐 **Async Engine**: Non-blocking asynchronous network transport powered by `httpx.AsyncClient`.

---

## Supported Specifications

- ✅ **Swagger 2.0** (Automatically normalized to OpenAPI 3.0 via the built-in adapter layer)
- ✅ **OpenAPI 3.0.x** (JSON and YAML)
- ✅ **OpenAPI 3.1.x** (JSON and YAML, including union `type` arrays, `oneOf` / `anyOf` / `allOf`, and `const`)

> **Note:** Swagger 2.0 is commonly referred to as OpenAPI 2.0.

### Compatibility Matrix

| Feature                                | Swagger 2.0 | OpenAPI 3.0 | OpenAPI 3.1 |
| -------------------------------------- | :---------: | :---------: | :---------: |
| Path / query / header / cookie params  | ✅          | ✅          | ✅          |
| `$ref` resolution (internal)           | ✅          | ✅          | ✅          |
| Base URL from `host` + `basePath`      | ✅          | —           | —           |
| Base URL from `servers[]`              | —           | ✅          | ✅          |
| Fallback base URL from spec source URL | ✅          | ✅          | ✅          |
| `application/json` request bodies      | ✅          | ✅          | ✅          |
| `application/x-www-form-urlencoded`    | ✅          | ✅          | ✅          |
| `multipart/form-data` (incl. files)    | ✅          | ✅          | ✅          |
| `text/*` and `application/xml`         | ✅          | ✅          | ✅          |
| Vendor `+json` media types             | ✅          | ✅          | ✅          |
| `oneOf` / `anyOf` (as Python `Union`)  | —           | ✅          | ✅          |
| `allOf` merge into single model        | —           | ✅          | ✅          |
| `nullable: true` (3.0)                 | —           | ✅          | —           |
| `type: ["string", "null"]` (3.1)       | —           | —           | ✅          |
| `const`                                | —           | —           | ✅          |
| `readOnly` / `writeOnly` / `deprecated`| ✅          | ✅          | ✅          |
| Security: Bearer / API key / Basic     | ✅          | ✅          | ✅          |
| Async execution (`httpx.AsyncClient`)  | ✅          | ✅          | ✅          |

Not yet supported: `discriminator`-driven union routing, `patternProperties`,
`$dynamicRef` / `$dynamicAnchor`, callbacks, links, webhooks, and XML request-body
serialization from Python dicts.

---

## Quick Start

```python
from langchain_openapi_tools import OpenAPIToolkit

# Load spec from remote URL or local file
toolkit = OpenAPIToolkit.from_url("https://api.crossref.org/swagger-docs")

# Extract generated tools
tools = toolkit.get_tools()

print(f"Generated {len(tools)} tools:")
for tool in tools[:3]:
    print(f"- {tool.name}: {tool.description}")
```

### Agent Integration

```python
import asyncio
from langchain_openapi_tools import OpenAPIToolkit


async def main():
    toolkit = OpenAPIToolkit.from_url("https://api.crossref.org/swagger-docs")
    search_tool = toolkit.get_tool("get_works")

    if search_tool:
        result = await search_tool.ainvoke({"query": "LangGraph"})
        print("Search Result:", result)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Execution Strategies: Typed, Generic & Hybrid

Large APIs can generate hundreds or thousands of typed tools, which blows up
prompts and slows agents. `langchain_openapi_tools` ships **three** execution
strategies that all share the same loader / parser / provider / middleware /
executor stack — only the LangChain interface changes.

| Toolkit | Best For | Tool Count |
| ------- | -------- | ---------- |
| **Typed** | Small & medium APIs, maximum correctness | One per operation |
| **Generic** | Large APIs, low context usage | Constant (9 tools) |
| **Hybrid** | Enterprise APIs mixing hot paths and long tails | Typed for selected ops + generic for the rest |

### Typed Toolkit (default)

```python
from langchain_openapi_tools import OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url(url)
tools = toolkit.get_tools()          # one StructuredTool per operation
```

### Generic Toolkit

```python
from langchain_openapi_tools import GenericOpenAPIToolkit

toolkit = GenericOpenAPIToolkit.from_url(url)
tools = toolkit.get_tools()          # constant set of tools
```

The generic toolkit always exposes:

- **HTTP tools** — `GET`, `POST`, `PUT`, `PATCH`, `DELETE`
- **Discovery tools** — `search_operations`, `describe_operation`,
  `list_operations`, `list_tags`

Intended reasoning flow:

```
user → search_operations("books")
     → describe_operation("get_books")
     → GET(endpoint="/books", params={...})
     → response
```

Nothing is duplicated: authentication providers, retry / rate-limit / cache /
logging / pagination middleware, and the async HTTP executor are all reused.

```python
from langchain_openapi_tools import (
    BearerAuthProvider,
    CacheMiddleware,
    GenericOpenAPIToolkit,
    InMemoryCacheBackend,
    RetryMiddleware,
)

toolkit = GenericOpenAPIToolkit.from_url(
    url,
    provider=BearerAuthProvider(token),
    middleware=[
        RetryMiddleware(retries=3),
        CacheMiddleware(backend=InMemoryCacheBackend(), ttl=60),
    ],
    timeout=30,
)
```

### Hybrid Toolkit

Mix strategies within the same toolkit — typed tools for the operations you
care about, generic HTTP tools for everything else.

```python
toolkit = GenericOpenAPIToolkit.from_url(url)

tools = toolkit.get_tools(
    mode="hybrid",
    typed_tags=["Books", "Users"],   # only these tags become typed tools
)
```

The classic `OpenAPIToolkit` also accepts `mode="generic"` / `mode="hybrid"`
and transparently delegates, so existing setups can opt in without switching
classes:

```python
toolkit = OpenAPIToolkit.from_url(url)
tools = toolkit.get_tools(mode="hybrid", typed_tags=["Books"])
```

---

## Prompt Optimization & Tool Customization

Large OpenAPI specifications can generate extensive tool descriptions that exceed model context windows. `langchain_openapi_tools` provides full control over description generation and context footprint.

### Configuration Object (`OpenAPIToolkitConfig`)

```python
from langchain_openapi_tools import OpenAPIToolkit, OpenAPIToolkitConfig

config = OpenAPIToolkitConfig(
    description_mode="compact",
    compress_descriptions=True,
    include_tags=["Works"],
    tool_description_overrides={
        "get_works": "Search scholarly papers registered with Crossref."
    },
)

toolkit = OpenAPIToolkit.from_url(
    "https://api.crossref.org/swagger-docs", config=config
)
```

### Description Modes (`description_mode`)

- `full` *(default)*: Complete summary, description, HTTP method, path, and schema parameter details.
- `compact`: Summary and short parameter list without response schemas or redundant examples.
- `minimal`: A single-sentence summary ideal for large specifications with dozens of tools.

```python
toolkit = OpenAPIToolkit.from_url(url, description_mode="minimal")
```

### Description Compression (`compress_descriptions=True`)

Removes duplicate text, redundant whitespace, and empty sections without altering tool semantics:

```python
toolkit = OpenAPIToolkit.from_url(url, compress_descriptions=True)
```

### Custom Overrides & Callbacks

Override descriptions for specific tools:

```python
toolkit = OpenAPIToolkit.from_url(
    url, tool_description_overrides={"get_works": "Search scholarly papers."}
)
```

Or pass a custom builder callback:

```python
def my_builder(operation):
    return f"Execute {operation.name} on path {operation.path}."


toolkit = OpenAPIToolkit.from_url(url, description_builder=my_builder)
```

### Operation Filtering

Filter tools before they are created to reduce context window overhead:

```python
# Filter by Tags
toolkit = OpenAPIToolkit.from_url(url, include_tags=["Works"], exclude_tags=["Admin"])

# Filter by Operations
toolkit = OpenAPIToolkit.from_url(
    url, include_operations=["get_works"], exclude_operations=["delete_work"]
)
```

---

## Architecture Pipeline

```text
          Swagger 2.0 / OpenAPI 3.x
                     │
                     ▼
            Swagger Normalizer
                     │
                     ▼
          Normalized OpenAPI Model
                     │
                     ▼
              Existing Parser
                     │
                     ▼
           Internal Operation Models
                     │
                     ▼
            Schema Converter
                     │
                     ▼
              HTTP Executor
                     │
                     ▼
          LangChain StructuredTools
```

### Example:

```python
from langchain_openapi_tools import OpenAPIToolkit
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

toolkit = OpenAPIToolkit.from_url(
    "https://api.crossref.org/swagger-docs"
)

model = init_chat_model("openrouter:qwen/qwen3-32b:free")

agent = create_agent(
    model=model,
    tools=toolkit.get_tools(tags=["Works"]),
)

response = agent.invoke({
    "messages": "Find papers about Kashmir"
})

```

---

## Why `langchain-openapi` Instead of the Alternatives?

Wiring an LLM up to a real API usually looks like one of these two extremes.
Neither works well in production.

### ❌ Option A — Hand-rolling one function per endpoint

The "just write it yourself" path:

```python
@tool
def list_pets(status: str) -> list[dict]:
    r = httpx.get(
        f"{BASE}/pets",
        params={"status": status},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    r.raise_for_status()
    return r.json()

# ...repeat 20, 200, or 2,000 times.
```

What you actually end up building yourself:

- One tool per operation, hand-copied from the docs.
- A Pydantic schema per tool, kept in sync with the spec — by hand.
- Bearer / API-key / Basic / OAuth2 / cookie plumbing on every call.
- Retry with exponential backoff, `Retry-After` handling, jitter.
- Token-bucket rate limiting so you do not get banned.
- Response caching with TTLs and cache-key hashing.
- Pagination aggregation across `next`, `Link`, `cursor`, offset styles.
- Log sanitization that strips secrets before they hit disk.
- A test suite that mocks every route with `respx`.
- A migration every time the vendor bumps the spec.

That is a **library**, not a feature. `langchain-openapi` is exactly that
library, already written, already tested against Petstore, Crossref, GitHub,
Stripe, and Kubernetes.

### ❌ Option B — Dropping the OpenAPI URL into the prompt

The "let the model figure it out" path:

```
System: Here is the API doc: https://api.example.com/openapi.json
User:   Please list all my pets.
```

Why this fails in practice:

- **Context explosion.** Real specs are 200 KB – 5 MB of JSON. That is a
  cold-start prompt tax on *every* turn.
- **Hallucinated endpoints.** Models happily invent `/users/{id}/pets`
  when the real path is `/pet/findByStatus`.
- **No auth.** The LLM cannot inject a Bearer token into a request it is
  only *describing*. You still have to build an executor.
- **No validation.** Nothing stops the model from sending
  `status="MAYBE"` when the enum is `[available, pending, sold]` — the
  server just 400s and the agent loops.
- **No middleware.** No retries, no rate limiting, no caching, no
  sanitized logging. The first 429 kills the run.
- **No reproducibility.** A doc URL that changes silently changes agent
  behaviour with zero code diff.

### ✅ `langchain-openapi`: the middle path

`langchain-openapi` treats the OpenAPI spec as the *source of truth* and
generates a strict, production-grade tool surface at runtime.

| Concern | Hand-rolled | LLM-reads-spec | **`langchain-openapi`** |
| ------- | ----------- | -------------- | ----------------------- |
| Tool generation | Manual | None | **Automatic from spec** |
| Pydantic argument validation | You write it | ❌ | **Generated per operation** |
| Path/query/header/cookie routing | You write it | ❌ | **Handled by `RequestBuilder`** |
| Bearer / API-Key / Basic / OAuth2 | You write it | ❌ | **Pluggable `RequestProvider`s** |
| Retry with backoff | You write it | ❌ | **`RetryMiddleware`** |
| Rate limiting | You write it | ❌ | **`RateLimitMiddleware`** |
| Response caching | You write it | ❌ | **`CacheMiddleware`** |
| Pagination aggregation | You write it | ❌ | **`PaginationMiddleware`** |
| Log sanitization | You write it | ❌ | **Built-in** |
| Prompt / context footprint | Grows linearly with endpoints | Grows with the whole spec | **Typed / Generic / Hybrid modes** |
| Endpoint discovery for large APIs | N/A | Full spec in prompt | **`search_operations` / `describe_operation`** |
| Swagger 2.0 · OpenAPI 3.0 · 3.1 | You port it | Model guesses | **Normalized by the adapter layer** |
| Spec changes | Manual diff | Silent drift | **Reload → new tools** |
| Testability | You write mocks | ❌ | **Deterministic, `respx`-friendly** |

### When to reach for it

- You have an API with **more than three endpoints** — the boilerplate
  savings already pay for themselves.
- You need **production-grade** networking (auth, retries, rate limits,
  caching, logging) without hand-rolling middleware.
- You want the **agent's tool schema to always match the spec** — no
  drift, no hallucinated parameters.
- You are targeting a **large surface** (GitHub, Kubernetes, Stripe) and
  want a *constant* prompt footprint via the Generic or Hybrid toolkit.
- You want the same integration to work across **Swagger 2.0, OpenAPI
  3.0, and OpenAPI 3.1** without a rewrite.

### TL;DR

Do not paste the OpenAPI URL into the prompt. Do not write 200 `@tool`
functions by hand. Point `langchain-openapi` at the spec and get
type-safe, authenticated, resilient LangChain tools — with your choice of
one-tool-per-operation, a constant generic surface, or a hybrid of both.
