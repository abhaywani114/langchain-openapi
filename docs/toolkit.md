# OpenAPIToolkit

`OpenAPIToolkit` is the primary entry point for converting OpenAPI specifications into native LangChain `StructuredTool` collections.

---

## Creation Methods

### Load from Remote URL

```python
from langchain_openapi import OpenAPIToolkit

toolkit = OpenAPIToolkit.from_url(
    "https://api.crossref.org/swagger-docs",
    headers={"User-Agent": "MyAgent/1.0"},
)
```

### Load from Local File

```python
toolkit = OpenAPIToolkit.from_file(
    "swagger.yaml",
)
```

### Load from Python Dictionary

```python
toolkit = OpenAPIToolkit.from_dict(
    spec_dict,
    base_url="https://api.example.com/v1",
)
```

---

## Tool Filtering & Selection

Filter generated tools by HTTP methods, tags, or operation names:

```python
# Filter by HTTP Method
read_only_toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/openapi.json",
    methods=["GET"],
)

# Filter by Tags
user_toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/openapi.json",
    tags=["Users", "Profiles"],
)

# Include specific operation names
included_toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/openapi.json",
    include=["get_user_by_id", "list_users"],
)

# Exclude specific operation names
excluded_toolkit = OpenAPIToolkit.from_url(
    "https://api.example.com/openapi.json",
    exclude=["delete_user_by_id"],
)
```

---

## Accessing Tools

```python
# Get list of all filtered tools
tools = toolkit.get_tools()

# Get single tool by operation name
tool = toolkit.get_tool("get_user_by_id")
```
