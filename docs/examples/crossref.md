# Crossref API Example

This example demonstrates using `langchain-openapi` with the public [Crossref REST API](https://api.crossref.org/swagger-docs) to search academic works and literature.

---

## Code Example

```python
import asyncio
from langchain_openapi import OpenAPIToolkit, RetryMiddleware, LoggingMiddleware


async def main():
    # 1. Initialize toolkit with retries and logging
    toolkit = OpenAPIToolkit.from_url(
        "https://api.crossref.org/swagger-docs",
        middleware=[
            LoggingMiddleware(),
            RetryMiddleware(retries=3),
        ],
    )

    # 2. Get tools
    tools = toolkit.get_tools()
    print(f"Loaded {len(tools)} tools from Crossref OpenAPI spec.")

    # 3. Execute search tool
    search_tool = toolkit.get_tool("search_works")
    if search_tool:
        result = await search_tool.ainvoke({"query": "LangChain"})
        print("Search Results:", result)


if __name__ == "__main__":
    asyncio.run(main())
```
