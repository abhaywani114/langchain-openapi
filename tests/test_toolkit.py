"""Unit tests for LangChainToolFactory and OpenAPIToolkit."""

from typing import Any

import pytest
import respx
from httpx import Response
from langchain_core.tools import BaseTool

from langchain_openapi_tools import (
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


def test_toolkit_config_description_modes() -> None:
    """Test description_mode options: full, compact, minimal."""
    op = Operation(
        name="get_works",
        method=HTTPMethod.GET,
        path="/works",
        operation_id="getWorks",
        summary="Search scholarly papers.",
        description="Returns list of works registered in Crossref.",
        parameters=[
            Parameter(
                name="query",
                location=ParameterLocation.QUERY,
                required=True,
                schema=Schema(type=DataType.STRING),
            )
        ],
    )

    from langchain_openapi_tools.toolkit import OpenAPIToolkitConfig

    # Minimal
    config_minimal = OpenAPIToolkitConfig(description_mode="minimal")
    desc_min = build_tool_description(op, config=config_minimal)
    assert desc_min == "Search scholarly papers."

    # Compact
    config_compact = OpenAPIToolkitConfig(description_mode="compact")
    desc_compact = build_tool_description(op, config=config_compact)
    assert "Search scholarly papers." in desc_compact
    assert "Parameters: query (query, required)" in desc_compact
    assert "HTTP Method:" not in desc_compact

    # Full
    config_full = OpenAPIToolkitConfig(description_mode="full")
    desc_full = build_tool_description(op, config=config_full)
    assert "Search scholarly papers." in desc_full
    assert "Returns list of works registered in Crossref." in desc_full
    assert "HTTP Method: GET" in desc_full


def test_toolkit_config_overrides_and_callback() -> None:
    """Test tool description overrides and custom builder callback."""
    op = Operation(
        name="get_works",
        method=HTTPMethod.GET,
        path="/works",
        operation_id="getWorks",
        summary="Default summary",
    )

    from langchain_openapi_tools.toolkit import OpenAPIToolkitConfig

    # Overrides
    config_override = OpenAPIToolkitConfig(
        tool_description_overrides={"get_works": "Search scholarly papers."}
    )
    desc_override = build_tool_description(
        op, tool_name="get_works", config=config_override
    )
    assert desc_override == "Search scholarly papers."

    # Callback
    def custom_builder(operation: Operation) -> str:
        return f"Custom builder for {operation.path}"

    config_callback = OpenAPIToolkitConfig(description_builder=custom_builder)
    desc_cb = build_tool_description(op, config=config_callback)
    assert desc_cb == "Custom builder for /works"


def test_toolkit_config_compression() -> None:
    """Test description prompt compression."""
    op = Operation(
        name="get_works",
        method=HTTPMethod.GET,
        path="/works",
        summary="Search scholarly papers.",
        description="Search scholarly papers.",
    )

    from langchain_openapi_tools.toolkit import OpenAPIToolkitConfig

    config = OpenAPIToolkitConfig(compress_descriptions=True)
    desc = build_tool_description(op, config=config)
    lines = desc.splitlines()
    assert lines.count("Search scholarly papers.") == 1


def test_toolkit_config_operation_filtering() -> None:
    """Test filtering operations via OpenAPIToolkitConfig."""
    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Filtered API", "version": "1.0.0"},
        "paths": {
            "/works": {
                "get": {
                    "operationId": "getWorks",
                    "tags": ["Works"],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/members": {
                "get": {
                    "operationId": "getMembers",
                    "tags": ["Members"],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/admin": {
                "delete": {
                    "operationId": "deleteAdmin",
                    "tags": ["Admin"],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }

    # 1. include_tags
    tk1 = OpenAPIToolkit.from_dict(spec_dict, include_tags=["Works"])
    assert tk1.list_tools() == ["get_works"]

    # 2. exclude_tags
    tk2 = OpenAPIToolkit.from_dict(spec_dict, exclude_tags=["Admin"])
    assert set(tk2.list_tools()) == {"get_works", "get_members"}

    # 3. include_operations
    tk3 = OpenAPIToolkit.from_dict(spec_dict, include_operations=["get_members"])
    assert tk3.list_tools() == ["get_members"]

    # 4. exclude_operations
    tk4 = OpenAPIToolkit.from_dict(spec_dict, exclude_operations=["delete_admin"])
    assert set(tk4.list_tools()) == {"get_works", "get_members"}
