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
- 🚀 **Swagger 2.0 & OpenAPI 3.x**: Native normalization of legacy Swagger 2.0 and modern OpenAPI 3.0/3.1 specs.
- 🗜️ **Prompt Optimization & Filtering**: Description modes (`full`, `compact`, `minimal`), description compression, overrides, callbacks, and operation/tag filtering to drastically reduce context window usage.
- 🔒 **Pluggable Authentication**: Built-in support for Bearer Tokens, API Key Headers, Query Parameters, Basic Auth, and custom request providers.
- 🛡️ **Production Middleware**: Composable middleware architecture for Retries (exponential backoff), Rate Limiting (token-bucket), Caching (TTL), Pagination aggregation, and Sanitized Logging.
- 🎯 **Type-Safe Validation**: Dynamically generated Pydantic input schemas ensure LLM arguments adhere strictly to specification types before network transport.
- 🌐 **Async Engine**: Non-blocking asynchronous network transport powered by `httpx.AsyncClient`.

---

## Supported Specifications

- ✅ **Swagger 2.0** (Automatically normalized to OpenAPI 3.0)
- ✅ **OpenAPI 3.0.x** (JSON and YAML)
- ✅ **OpenAPI 3.1.x** (JSON and YAML)

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
