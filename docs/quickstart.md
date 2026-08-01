# Quickstart Guide

Get up and running with `langchain-openapi` in five minutes.

---

## 1. Load an OpenAPI Specification

`OpenAPIToolkit` provides convenient class methods to load specs from URLs, local files, or raw dictionaries.

```python
from langchain_openapi_tools import OpenAPIToolkit

# Load from URL
toolkit = OpenAPIToolkit.from_url("https://api.crossref.org/swagger-docs")

# Load from local YAML/JSON file
# toolkit = OpenAPIToolkit.from_file("openapi.yaml")

# Load from dictionary
# toolkit = OpenAPIToolkit.from_dict(spec_dict)
```

---

## 2. Inspect Generated Tools

Call `.get_tools()` to obtain native LangChain `StructuredTool` instances.

```python
tools = toolkit.get_tools()

for tool in tools[:3]:
    print(f"Name: {tool.name}")
    print(f"Description: {tool.description}")
    print("---")
```

---

## 3. Invoke a Tool Directly

You can invoke tools synchronously (`tool.invoke`) or asynchronously (`tool.ainvoke`):

```python
import asyncio


async def main():
    tool = toolkit.get_tool("search_works")
    result = await tool.ainvoke({"query": "LangGraph"})
    print(result)


asyncio.run(main())
```

---

## 4. Bind Tools to a LangChain Agent

Bind generated tools to an agent or LLM framework:

```python
from langchain_openapi_tools import OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url("https://api.crossref.org/swagger-docs")
tools = toolkit.get_tools()

# Bind to LLM
# llm_with_tools = llm.bind_tools(tools)
```

---

## 5. Scale to Large APIs

For APIs with hundreds of operations (GitHub, Kubernetes, Stripe...) the
typed toolkit's one-tool-per-operation strategy can blow the prompt
window. Switch to the
[`GenericOpenAPIToolkit`](generic_toolkit.md) for a constant tool count
regardless of API size:

```python
from langchain_openapi_tools import GenericOpenAPIToolkit

toolkit = GenericOpenAPIToolkit.from_url(
    "https://petstore3.swagger.io/api/v3/openapi.json"
)

tools = toolkit.get_tools()  # GET/POST/PUT/PATCH/DELETE + discovery helpers
```

Or mix both strategies with hybrid mode:

```python
tools = toolkit.get_tools(mode="hybrid", typed_tags=["Pet"])
```

See the [Generic & Hybrid Toolkits guide](generic_toolkit.md) for the
full walkthrough.
