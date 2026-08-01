# Swagger Petstore Example

This example demonstrates interacting with the classic Swagger Petstore API using `langchain-openapi`.

---

## Code Example

```python
import asyncio
from langchain_openapi_tools import OpenAPIToolkit, LoggingMiddleware


async def main():
    toolkit = OpenAPIToolkit.from_url(
        "https://petstore.swagger.io/v2/swagger.json",
        middleware=[LoggingMiddleware()],
    )

    tools = toolkit.get_tools()
    print(f"Loaded {len(tools)} Petstore tools.")

    find_by_status = toolkit.get_tool("find_pets_by_status")
    if find_by_status:
        res = await find_by_status.ainvoke({"status": ["available"]})
        print("Available Pets:", res)


if __name__ == "__main__":
    asyncio.run(main())
```
