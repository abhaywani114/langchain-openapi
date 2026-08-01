"""Unit tests for LangChainToolFactory and OpenAPIToolkit."""

from typing import Any

import pytest
import respx
from httpx import Response
from langchain_core.tools import BaseTool

from langchain_openapi import (
    DataType,
    HTTPMethod,
    LangChainToolFactory,
    OpenAPIToolkit,
    Operation,
    Parameter,
    ParameterLocation,
    Schema,
    build_tool_description,
    format_tool_name,
)


def test_tool_naming_and_description() -> None:
    """Test format_tool_name and build_tool_description logic."""
    op_with_id = Operation(
        name="op1",
        method=HTTPMethod.GET,
        path="/works",
        operation_id="searchWorks",
        summary="Search scholarly works.",
        description="Returns matching publications.",
    )
    assert format_tool_name(op_with_id) == "search_works"

    op_with_summary = Operation(
        name="op2",
        method=HTTPMethod.POST,
        path="/pets",
        summary="Create a new pet",
    )
    assert format_tool_name(op_with_summary) == "create_a_new_pet"

    desc = build_tool_description(op_with_id)
    assert "Search scholarly works." in desc
    assert "Returns matching publications." in desc
    assert "HTTP Method: GET" in desc
    assert "Path: /works" in desc


def test_factory_creates_structured_tool() -> None:
    """Test LangChainToolFactory converts Operation to StructuredTool with metadata."""
    op = Operation(
        name="getPet",
        method=HTTPMethod.GET,
        path="/pets/{petId}",
        summary="Find pet by ID",
        tags=["Pet"],
        parameters=[
            Parameter(
                name="petId",
                location=ParameterLocation.PATH,
                required=True,
                schema=Schema(type=DataType.INTEGER),
            )
        ],
    )

    factory = LangChainToolFactory()
    tool = factory.create_tool(op)

    assert isinstance(tool, BaseTool)
    assert tool.name == "find_pet_by_id"
    assert tool.metadata is not None
    assert tool.metadata["method"] == "GET"
    assert tool.metadata["path"] == "/pets/{petId}"
    assert tool.metadata["tags"] == ["Pet"]

    # Verify Pydantic args_schema
    assert tool.args_schema is not None
    assert hasattr(tool.args_schema, "model_fields")
    fields = list(tool.args_schema.model_fields.keys())
    assert "petId" in fields


@pytest.mark.asyncio
@respx.mock
async def test_async_tool_execution() -> None:
    """Test executing a generated tool asynchronously via ainvoke."""
    respx.get("https://api.example.com/v1/works?query=LangChain").mock(
        return_value=Response(200, json={"total-results": 42, "items": []})
    )

    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Works API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com/v1"}],
        "paths": {
            "/works": {
                "get": {
                    "operationId": "searchWorks",
                    "summary": "Search works",
                    "tags": ["Works"],
                    "parameters": [
                        {
                            "name": "query",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    toolkit = OpenAPIToolkit.from_dict(spec_dict)
    tools = toolkit.get_tools()

    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "search_works"

    # Async execution
    result = await tool.ainvoke({"query": "LangChain"})
    assert result == {"total-results": 42, "items": []}


@pytest.mark.asyncio
@respx.mock
async def test_tool_execution_error_handling() -> None:
    """Test tool execution catches API errors and raises ToolException."""
    respx.get("https://api.example.com/fail").mock(return_value=Response(500))

    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Error API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/fail": {
                "get": {
                    "operationId": "failOp",
                    "responses": {"500": {"description": "Error"}},
                }
            }
        },
    }

    toolkit = OpenAPIToolkit.from_dict(spec_dict)
    tool = toolkit.get_tool("fail_op")

    # Sync invocation wrapping with handle_tool_error=True
    # LangChain's handle_tool_error catches ToolException and returns error string
    res = tool.invoke({})
    assert "HTTP request failed with status code 500" in str(res)


def test_toolkit_filtering() -> None:
    """Test toolkit filtering by HTTP method, tags, include, and exclude."""
    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Petstore", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "tags": ["Pet"],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "createPet",
                    "tags": ["Pet"],
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/store/inventory": {
                "get": {
                    "operationId": "getInventory",
                    "tags": ["Store"],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }

    toolkit = OpenAPIToolkit.from_dict(spec_dict)

    # 1. List all tools
    all_tools = toolkit.list_tools()
    assert set(all_tools) == {"list_pets", "create_pet", "get_inventory"}

    # 2. Filter by method
    get_tools = toolkit.get_tools(methods=["GET"])
    assert {t.name for t in get_tools} == {"list_pets", "get_inventory"}

    # 3. Filter by tags
    store_tools = toolkit.get_tools(tags=["Store"])
    assert len(store_tools) == 1
    assert store_tools[0].name == "get_inventory"

    # 4. Include filter
    inc_tools = toolkit.get_tools(include=["create_pet"])
    assert len(inc_tools) == 1
    assert inc_tools[0].name == "create_pet"

    # 5. Exclude filter
    exc_tools = toolkit.get_tools(exclude=["list_pets"])
    assert {t.name for t in exc_tools} == {"create_pet", "get_inventory"}


def test_toolkit_get_tool_by_name() -> None:
    """Test get_tool returns single tool or raises KeyError."""
    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Simple API", "version": "1.0.0"},
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "ping",
                    "responses": {"200": {"description": "Pong"}},
                }
            }
        },
    }

    toolkit = OpenAPIToolkit.from_dict(spec_dict)
    tool = toolkit.get_tool("ping")
    assert tool.name == "ping"

    with pytest.raises(KeyError) as exc_info:
        toolkit.get_tool("non_existent_tool")

    assert "Tool 'non_existent_tool' not found in toolkit" in str(exc_info.value)
