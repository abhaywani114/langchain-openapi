# langchain-openapi

<p align="center">
  <!-- Logo Placeholder -->
  <img src="docs/assets/logo.png" alt="langchain-openapi logo" width="200" onerror="this.style.display='none'"/>
</p>

<p align="center">
  <em>Convert OpenAPI v3.0 & v3.1 specifications into native, production-grade LangChain tools.</em>
</p>

<p align="center">
  <a href="https://github.com/abhaywani114/langchain-openapi/actions/workflows/ci.yml"><img src="https://github.com/abhaywani114/langchain-openapi/actions/workflows/ci.yml/badge.svg" alt="CI Status"/></a>
  <a href="https://pypi.org/project/langchain-openapi/"><img src="https://img.shields.io/pypi/v/langchain-openapi.svg" alt="PyPI Version"/></a>
  <a href="https://abhaywani114.github.io/langchain-openapi/"><img src="https://img.shields.io/badge/docs-mkdocs-blue.svg" alt="Documentation"/></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"/></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/code%20style-ruff-000000.svg" alt="Code Style: Ruff"/></a>
  <a href="http://mypy-lang.org/"><img src="https://img.shields.io/badge/mypy-checked-blue.svg" alt="Checked with MyPy"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"/></a>
</p>

---

`langchain_openapi` is a modern Python library designed to seamlessly convert OpenAPI v3.0 and v3.1 specifications into native, type-safe [LangChain](https://github.com/langchain-ai/langchain) tools for AI agents and LLM applications.

No python code generation is required—tools are generated dynamically at runtime with strict Pydantic input schemas and production-ready middleware.

---

## Features

- ⚡ **Zero-Code Tool Generation**: Runtime conversion of OpenAPI specs (YAML/JSON) into LangChain `StructuredTool`s.
- 🔒 **Pluggable Authentication**: Built-in support for Bearer Tokens, API Key Headers, Query Parameters, Basic Auth, and custom request providers.
- 🛡️ **Production Middleware**: Composable middleware architecture for Retries (exponential backoff), Rate Limiting (token-bucket), Caching (TTL), Pagination aggregation, and Sanitized Logging.
- 🎯 **Type-Safe Validation**: Dynamically generated Pydantic input schemas ensure LLM arguments adhere strictly to specification types before network transport.
- 🌐 **Async Engine**: Non-blocking asynchronous network transport powered by `httpx.AsyncClient`.

---

## Supported Specifications

- ✅ **OpenAPI 3.0.x** (JSON and YAML)
- ✅ **OpenAPI 3.1.x** (JSON and YAML)
- ❌ **Swagger 2.0** (Explicitly rejected with descriptive error)

---

## Quick Start

### Installation

```bash
uv add langchain-openapi
# or
pip install langchain-openapi
```

### Basic Usage

```python
from langchain_openapi import OpenAPIToolkit

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
from langchain_openapi import OpenAPIToolkit


async def main():
    toolkit = OpenAPIToolkit.from_url("https://api.crossref.org/swagger-docs")
    search_tool = toolkit.get_tool("search_works")

    if search_tool:
        result = await search_tool.ainvoke({"query": "LangGraph"})
        print("Search Result:", result)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Architecture

```text
OpenAPI Specification (JSON / YAML)
             │
             ▼
      OpenAPILoader
             │
             ▼
       OpenAPIParser ───► ReferenceResolver ($ref)
             │
             ▼
     SchemaConverter ───► Dynamic Pydantic Input Models
             │
             ▼
   LangChainToolFactory ───► LangChain StructuredTool
             │
             ▼
     AsyncHTTPExecutor
             │
             ▼
    Middleware Pipeline (Retry, RateLimit, Cache, Pagination, Logging)
             │
             ▼
    Request Providers (Authentication & Custom Headers)
             │
             ▼
        httpx.AsyncClient (HTTP Target API)
```

---

## Authentication Methods

`langchain_openapi` supports pluggable authentication via `RequestProvider` classes:

```python
from langchain_openapi import (
    APIKeyHeaderProvider,
    BasicAuthProvider,
    BearerAuthProvider,
    CompositeProvider,
    OpenAPIToolkit,
)

# 1. Bearer Token Auth
toolkit_bearer = OpenAPIToolkit.from_url(
    "https://api.github.com/openapi",
    provider=BearerAuthProvider(token="secret_token"),
)

# 2. API Key Header Auth
toolkit_apikey = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    provider=APIKeyHeaderProvider(key="secret_key", header="X-API-Key"),
)

# 3. Composite Provider (Multiple authentication schemes)
composite = CompositeProvider(
    [
        BearerAuthProvider(token="secret_jwt"),
        APIKeyHeaderProvider(key="secret_key", header="X-API-Key"),
    ]
)

toolkit_composite = OpenAPIToolkit.from_url(
    "https://api.example.com/spec.json",
    provider=composite,
)
```

---

## Production Middleware & Resilience

Intercept requests and responses to apply cross-cutting resilience concerns:

```python
from langchain_openapi import (
    CacheMiddleware,
    LoggingMiddleware,
    OpenAPIToolkit,
    PaginationMiddleware,
    RateLimitMiddleware,
    RetryMiddleware,
)

toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/openapi.json",
    middleware=[
        LoggingMiddleware(),
        RetryMiddleware(retries=3, backoff="exponential"),
        RateLimitMiddleware(requests_per_second=10.0),
        CacheMiddleware(ttl=300.0),
        PaginationMiddleware(max_pages=10),
    ],
)
```

---

## Example Applications

Runnable example projects are located in `examples/`:

- 📚 [`examples/crossref`](examples/crossref/): Academic works search via Crossref API.
- 🐙 [`examples/github`](examples/github/): Repository search via GitHub REST API with Bearer Token.
- 🐶 [`examples/petstore`](examples/petstore/): Pet store management using Swagger Petstore.
- 📝 [`examples/jsonplaceholder`](examples/jsonplaceholder/): REST resource querying with caching.

---

## Roadmap

- ✅ **Milestone 1**: Project Foundation & Tooling
- ✅ **Milestone 2**: OpenAPI Specification Loader
- ✅ **Milestone 3**: OpenAPI Parser & Data Models
- ✅ **Milestone 4**: Dynamic Pydantic Schema Converter
- ✅ **Milestone 5**: Async HTTP Executor Engine
- ✅ **Milestone 6**: LangChain Tool Factory & Toolkit
- ✅ **Milestone 7**: Authentication & Request Providers
- ✅ **Milestone 8**: Production Middleware & Resilience Pipeline
- ✅ **Milestone 9**: Open Source Readiness & Documentation
- ⏳ **Milestone 10**: v1.0 Release Candidate & PyPI Publish

---

## Development & Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on code style, testing, and pull request procedures.

```bash
# Sync virtual environment
uv sync --extra dev

# Run all checks (format, lint, mypy, pytest, docs build, benchmark)
make all
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
