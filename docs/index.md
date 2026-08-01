# langchain-openapi-tools

> Convert OpenAPI specifications into native, production-grade LangChain tools for AI agents.

`langchain_openapi` automatically parses OpenAPI v3.0 and v3.1 specifications and generates dynamic, strongly typed [LangChain](https://github.com/langchain-ai/langchain) `StructuredTool`s. No code generation or manual tool writing is required.

---

## Key Features

- ⚡ **Zero-Code Tool Generation**: Instant runtime conversion from OpenAPI JSON/YAML to LangChain tools.
- 🧭 **Typed, Generic & Hybrid Toolkits**: Choose per-operation typed tools, a constant set of generic `GET`/`POST`/... tools with on-demand endpoint discovery, or a hybrid mix — all sharing the same execution stack.
- 🔒 **Comprehensive Authentication**: Built-in support for Bearer Tokens, API Keys, Basic Auth, Cookies, and custom request providers.
- 🛡️ **Production Middleware Pipeline**: Onion-style request/response interceptors for retries, rate-limiting, caching, logging, and result pagination.
- 🎯 **Type-Safe Validation**: Dynamic Pydantic schema generation ensures LLM inputs are validated before HTTP execution.
- 🌐 **Async & Sync Support**: Fully asynchronous execution engine powered by `httpx`.

---

## Quick Example

```python
from langchain_openapi_tools import OpenAPIToolkit

# Load spec from remote URL or local file
toolkit = OpenAPIToolkit.from_url("https://api.crossref.org/swagger-docs")

# Get dynamically generated LangChain tools
tools = toolkit.get_tools()

print(f"Generated {len(tools)} tools:")
for tool in tools:
    print(f"- {tool.name}: {tool.description}")
```

---

## Navigation

- [Installation](installation.md)
- [Quickstart Guide](quickstart.md)
- [Architecture](architecture.md)
- [Authentication & Request Providers](authentication.md)
- [Production Middleware](middleware.md)
- [Generic & Hybrid Toolkits](generic_toolkit.md)
- [API Reference](api/toolkit.md)
