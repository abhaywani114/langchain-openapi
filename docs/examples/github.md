# GitHub REST API Example

This example demonstrates authenticating with the GitHub REST API using `BearerAuthProvider` and executing repository search operations.

---

## Code Example

```python
import os
import asyncio
from langchain_openapi import (
    OpenAPIToolkit,
    BearerAuthProvider,
    RateLimitMiddleware,
)


async def main():
    token = os.getenv("GITHUB_TOKEN", "")
    provider = BearerAuthProvider(token=token) if token else None

    # Load GitHub spec or dictionary
    toolkit = OpenAPIToolkit.from_url(
        "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json",
        provider=provider,
        middleware=[RateLimitMiddleware(requests_per_second=2.0)],
        tags=["search"],
    )

    tools = toolkit.get_tools()
    print(f"Loaded {len(tools)} GitHub search tools.")


if __name__ == "__main__":
    asyncio.run(main())
```
