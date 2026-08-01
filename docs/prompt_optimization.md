# Prompt Optimization & Context Window Management

Large OpenAPI specifications (e.g. Crossref, GitHub, Slack) contain extensive operation descriptions, parameter documentation, and schema definitions. Passing raw specifications or unoptimized tools directly into an LLM context window can lead to context exhaustion, high latency, and elevated API costs.

`langchain_openapi` includes built-in prompt optimization tools to compress tool descriptions and filter unnecessary operations before tool creation.

---

## The `OpenAPIToolkitConfig` Configuration Object

Customize tool creation behavior by initializing an `OpenAPIToolkitConfig` object and passing it to `OpenAPIToolkit`:

```python
from langchain_openapi_tools import OpenAPIToolkit, OpenAPIToolkitConfig

config = OpenAPIToolkitConfig(
    description_mode="compact",
    compress_descriptions=True,
    include_tags=["Works"],
    tool_description_overrides={
        "get_works": "Search scholarly publications in Crossref."
    },
)

toolkit = OpenAPIToolkit.from_url(
    "https://api.crossref.org/swagger-docs", config=config
)
```

Alternatively, pass keyword arguments directly for convenience:

```python
toolkit = OpenAPIToolkit.from_url(
    "https://api.crossref.org/swagger-docs",
    description_mode="compact",
    compress_descriptions=True,
    include_tags=["Works"],
)
```

---

## Tool Description Modes (`description_mode`)

`langchain_openapi` supports three description modes:

### 1. `full` (Default)
Includes the full operation summary, full description, HTTP method, and path:

```text
Search scholarly works registered with Crossref.

Returns metadata for matching DOI entries.

HTTP Method: GET
Path: /works
```

### 2. `compact`
Includes only a single-line summary and a concise parameter list, omitting HTTP method, path, response schemas, and examples:

```text
Search scholarly works.
Parameters: query (query, required), rows (query), offset (query)
```

### 3. `minimal`
Includes a single sentence. Best for APIs with dozens of endpoints to minimize context usage:

```text
Search scholarly works.
```

---

## Description Compression (`compress_descriptions=True`)

Enable description compression to automatically:
- Remove duplicate sentences (e.g., when `summary` repeats `description`).
- Strip redundant formatting, empty sections, and extra whitespace.
- Omit response schemas and non-essential examples.

```python
toolkit = OpenAPIToolkit.from_url(url, compress_descriptions=True)
```

---

## Description Overrides & Callback Builders

### Tool Description Overrides

Directly override tool descriptions for specific operations:

```python
toolkit = OpenAPIToolkit.from_url(
    url,
    tool_description_overrides={
        "get_works": "Search Crossref papers by keyword or DOI."
    },
)
```

### Custom Builder Callback

Pass a callback function that receives the `Operation` model and returns a custom string:

```python
def custom_builder(operation):
    return f"Execute {operation.name} against endpoint {operation.path}."


toolkit = OpenAPIToolkit.from_url(url, description_builder=custom_builder)
```

---

## Operation & Tag Filtering

Filter endpoints before generating LangChain tools to avoid creating unused tools:

### Filter by Tags

```python
# Only create tools for the 'Works' tag
toolkit = OpenAPIToolkit.from_url(url, include_tags=["Works"])

# Exclude internal or admin endpoints
toolkit = OpenAPIToolkit.from_url(url, exclude_tags=["Admin"])
```

### Filter by Operations

```python
# Specify exact operations to include
toolkit = OpenAPIToolkit.from_url(url, include_operations=["get_works", "get_members"])

# Exclude destructive operations
toolkit = OpenAPIToolkit.from_url(url, exclude_operations=["delete_work"])
```
