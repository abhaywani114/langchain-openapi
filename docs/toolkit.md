# OpenAPIToolkit

`OpenAPIToolkit` is the primary entry point for converting OpenAPI specifications into native LangChain `StructuredTool` collections.

---

## Creation Methods

### Load from Remote URL

```python
from langchain_openapi_tools import OpenAPIToolkit

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

## Base URL Resolution

The toolkit determines the base URL used for HTTP requests in this order of precedence:

1. Explicit `base_url` argument passed to `OpenAPIToolkit.__init__` / `from_url` / `from_file` / `from_dict`.
2. The first entry in the spec's `servers` block (OpenAPI 3.x) or the URL synthesized from `host`/`basePath`/`schemes` (Swagger 2.0).
3. When `OpenAPIToolkit.from_url(...)` is used and the spec has no `servers` (or Swagger 2.0 has no `host`), the source URL is used as a fallback: relative server URLs are resolved against it via `urljoin`, and a missing `servers` block defaults to the document's `scheme://host` origin — matching the OpenAPI 3.x specification.

This means self-describing endpoints such as `https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json` (an OpenAPI 3.0.1 document that omits the `servers` block) work out of the box without a manual `base_url`. For local files or in-memory dicts with no `servers`, pass `base_url` explicitly.

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
