"""Swagger Petstore Example using langchain-openapi."""

import asyncio
from pathlib import Path

from langchain_openapi_tools import LoggingMiddleware, OpenAPIToolkit


async def main() -> None:
    """Run Swagger Petstore API example."""
    spec_path = Path(__file__).parent / "petstore.json"
    print("Loading Swagger Petstore specification...")
    toolkit = OpenAPIToolkit.from_file(
        spec_path,
        middleware=[LoggingMiddleware()],
    )

    tools = toolkit.get_tools()
    print(f"Generated {len(tools)} Petstore tools.")

    find_by_status = toolkit.get_tool("find_pets_by_status")
    if find_by_status:
        print("Executing find_pets_by_status...")
        result = await find_by_status.ainvoke({"status": "available"})
        count = len(result) if isinstance(result, list) else "N/A"
        print(f"Retrieved pets count: {count}")


if __name__ == "__main__":
    asyncio.run(main())
