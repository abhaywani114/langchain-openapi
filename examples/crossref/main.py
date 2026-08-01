"""Crossref API Example using langchain-openapi."""

import asyncio
from pathlib import Path

from langchain_openapi_tools import LoggingMiddleware, OpenAPIToolkit, RetryMiddleware


async def main() -> None:
    """Run Crossref API search example."""
    spec_path = Path(__file__).parent / "crossref.json"
    print("Loading Crossref OpenAPI specification...")
    toolkit = OpenAPIToolkit.from_file(
        spec_path,
        middleware=[
            LoggingMiddleware(),
            RetryMiddleware(retries=3),
        ],
    )

    tools = toolkit.get_tools()
    print(f"Generated {len(tools)} tools from Crossref spec.")

    search_tool = toolkit.get_tool("search_works")
    if search_tool:
        print("\nInvoking 'search_works' tool...")
        result = await search_tool.ainvoke({"query": "LangChain"})
        res_count = (
            result.get("message", {}).get("total-results")
            if isinstance(result, dict)
            else "N/A"
        )
        print(f"Result total results: {res_count}")


if __name__ == "__main__":
    asyncio.run(main())
