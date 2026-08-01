"""End-to-end integration tests for langchain-openapi."""

from typing import Any

import httpx
import pytest
import respx
from langchain_core.tools import BaseTool

from langchain_openapi_tools import (
    BearerAuthProvider,
    CacheMiddleware,
    LoggingMiddleware,
    OpenAPIToolkit,
    PaginationMiddleware,
    RateLimitMiddleware,
    RetryMiddleware,
)


@pytest.mark.e2e
@pytest.mark.asyncio
@respx.mock
async def test_e2e_jsonplaceholder_pipeline() -> None:
    """E2E test verifying load, parse, tool generation, and middleware."""
    respx.get("https://jsonplaceholder.typicode.com/posts/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "userId": 1,
                "id": 1,
                "title": "sunt aut facere",
                "body": "quia et suscipit",
            },
        )
    )

    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "JSONPlaceholder API", "version": "1.0.0"},
        "servers": [{"url": "https://jsonplaceholder.typicode.com"}],
        "paths": {
            "/posts/{id}": {
                "get": {
                    "operationId": "getPostById",
                    "summary": "Get post by ID",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    # 1. Load & Parse spec into Toolkit with Middleware & Authentication Provider
    toolkit = OpenAPIToolkit.from_dict(
        spec_dict,
        provider=BearerAuthProvider(token="e2e_dummy_token"),
        middleware=[
            LoggingMiddleware(),
            RetryMiddleware(retries=2),
            CacheMiddleware(ttl=60.0, cache_authenticated=True),
            RateLimitMiddleware(requests_per_second=50.0),
        ],
    )

    # 2. Extract tools
    tools = toolkit.get_tools()
    assert len(tools) == 1
    tool = tools[0]
    assert isinstance(tool, BaseTool)
    assert tool.name == "get_post_by_id"

    # 3. Execute tool asynchronously (ainvoke)
    res1 = await tool.ainvoke({"id": 1})
    assert isinstance(res1, dict)
    assert res1["id"] == 1
    assert res1["userId"] == 1

    # 4. Execute tool synchronously (invoke - tests sync wrapper)
    res2 = tool.invoke({"id": 1})
    assert isinstance(res2, dict)
    assert res2["id"] == 1


@pytest.mark.e2e
@pytest.mark.asyncio
@respx.mock
async def test_e2e_pagination_pipeline() -> None:
    """E2E test verifying automated multi-page aggregation in tool invocation."""
    respx.get("https://api.example.com/items?page=2").mock(
        return_value=httpx.Response(200, json={"items": [{"id": 3}, {"id": 4}]})
    )
    respx.get("https://api.example.com/items").mock(
        return_value=httpx.Response(200, json={"items": [{"id": 1}, {"id": 2}]})
    )

    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Paginated API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/items": {
                "get": {
                    "operationId": "listItems",
                    "summary": "List paginated items",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    toolkit = OpenAPIToolkit.from_dict(
        spec_dict,
        middleware=[PaginationMiddleware(max_pages=2)],
    )

    tool = toolkit.get_tool("list_items")
    assert tool is not None

    res = await tool.ainvoke({"paginate": True})
    assert res == {"items": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]}
