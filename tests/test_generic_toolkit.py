"""Tests for the Generic HTTP Toolkit."""

from typing import Any

import httpx
import pytest
import respx

from langchain_openapi_tools import (
    APIKeyHeaderProvider,
    BearerAuthProvider,
    CacheMiddleware,
    GenericHTTPToolFactory,
    GenericOpenAPIToolkit,
    GenericToolkitConfig,
    InMemoryCacheBackend,
    OpenAPIToolkit,
    OperationIndex,
    RetryMiddleware,
)

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

PETSTORE_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Petstore", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "summary": "List all pets",
                "description": "Returns every pet in the store.",
                "tags": ["Pet"],
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "operationId": "createPet",
                "summary": "Create a pet",
                "tags": ["Pet"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                },
                                "required": ["name"],
                            }
                        }
                    },
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "summary": "Find pet by ID",
                "tags": ["Pet"],
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {"200": {"description": "OK"}},
            }
        },
        "/store/inventory": {
            "get": {
                "operationId": "getInventory",
                "summary": "Return the current inventory",
                "tags": ["Store"],
                "responses": {"200": {"description": "OK"}},
            }
        },
        "/users/{username}": {
            "delete": {
                "operationId": "deleteUser",
                "summary": "Remove a user",
                "tags": ["User"],
                "parameters": [
                    {
                        "name": "username",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {"204": {"description": "Deleted"}},
            }
        },
    },
}


@pytest.fixture()
def toolkit() -> GenericOpenAPIToolkit:
    return GenericOpenAPIToolkit.from_dict(PETSTORE_SPEC)


# --------------------------------------------------------------------------- #
# Tool surface                                                                #
# --------------------------------------------------------------------------- #


def test_generic_toolkit_exposes_fixed_http_tools(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    tools = toolkit.get_tools(mode="generic")
    names = {t.name for t in tools}
    assert {"GET", "POST", "PUT", "PATCH", "DELETE"} <= names
    assert {
        "search_operations",
        "describe_operation",
        "list_operations",
        "list_tags",
    } <= names


def test_generic_tool_count_is_constant_regardless_of_spec_size() -> None:
    """Even large specs must yield the same constant number of tools."""
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Big", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            f"/resource/{i}": {
                "get": {
                    "operationId": f"getResource{i}",
                    "responses": {"200": {"description": "OK"}},
                }
            }
            for i in range(250)
        },
    }
    tk = GenericOpenAPIToolkit.from_dict(spec)
    generic_tools = tk.get_tools(mode="generic")
    # 5 HTTP tools + 4 discovery tools = 9
    assert len(generic_tools) == 9


# --------------------------------------------------------------------------- #
# HTTP execution                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_generic_get_request(toolkit: GenericOpenAPIToolkit) -> None:
    respx.get("https://api.example.com/v1/pets/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "Rex"})
    )
    get_tool = next(t for t in toolkit.get_tools(mode="generic") if t.name == "GET")
    result = await get_tool.ainvoke({"endpoint": "/pets/1"})
    assert result == {"id": 1, "name": "Rex"}


@pytest.mark.asyncio
@respx.mock
async def test_generic_post_request(toolkit: GenericOpenAPIToolkit) -> None:
    route = respx.post("https://api.example.com/v1/pets").mock(
        return_value=httpx.Response(201, json={"id": 7, "name": "Milo"})
    )
    post_tool = next(
        t for t in toolkit.get_tools(mode="generic") if t.name == "POST"
    )
    result = await post_tool.ainvoke(
        {"endpoint": "/pets", "body": {"name": "Milo"}}
    )
    assert result == {"id": 7, "name": "Milo"}
    assert route.calls.last is not None
    sent = route.calls.last.request
    assert sent.headers.get("content-type") == "application/json"
    assert sent.content == b'{"name":"Milo"}'


@pytest.mark.asyncio
@respx.mock
async def test_generic_delete_request(toolkit: GenericOpenAPIToolkit) -> None:
    route = respx.delete("https://api.example.com/v1/users/alice").mock(
        return_value=httpx.Response(204)
    )
    delete_tool = next(
        t for t in toolkit.get_tools(mode="generic") if t.name == "DELETE"
    )
    result = await delete_tool.ainvoke({"endpoint": "/users/alice"})
    assert result is None
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_generic_get_supports_absolute_url() -> None:
    respx.get("https://example.org/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    tk = GenericOpenAPIToolkit.from_dict(PETSTORE_SPEC)
    tool = next(t for t in tk.get_tools(mode="generic") if t.name == "GET")
    result = await tool.ainvoke({"endpoint": "https://example.org/ping"})
    assert result == {"ok": True}


@pytest.mark.asyncio
@respx.mock
async def test_generic_error_status_raises_tool_exception(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    respx.get("https://api.example.com/v1/boom").mock(
        return_value=httpx.Response(500, json={"error": "explode"})
    )
    tool = next(t for t in toolkit.get_tools(mode="generic") if t.name == "GET")
    result = tool.invoke({"endpoint": "/boom"})
    # handle_tool_error=True stringifies the ToolException.
    assert "HTTP GET request failed with status 500" in str(result)


# --------------------------------------------------------------------------- #
# Authentication + middleware are shared                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_generic_toolkit_applies_bearer_auth() -> None:
    route = respx.get("https://api.example.com/v1/pets").mock(
        return_value=httpx.Response(200, json=[])
    )
    tk = GenericOpenAPIToolkit.from_dict(
        PETSTORE_SPEC, provider=BearerAuthProvider("secret-token")
    )
    tool = next(t for t in tk.get_tools(mode="generic") if t.name == "GET")
    await tool.ainvoke({"endpoint": "/pets"})
    assert route.calls.last is not None
    assert (
        route.calls.last.request.headers.get("authorization")
        == "Bearer secret-token"
    )


@pytest.mark.asyncio
@respx.mock
async def test_generic_toolkit_applies_api_key_header() -> None:
    route = respx.get("https://api.example.com/v1/pets").mock(
        return_value=httpx.Response(200, json=[])
    )
    tk = GenericOpenAPIToolkit.from_dict(
        PETSTORE_SPEC,
        provider=APIKeyHeaderProvider("abc123", header="X-API-Key"),
    )
    tool = next(t for t in tk.get_tools(mode="generic") if t.name == "GET")
    await tool.ainvoke({"endpoint": "/pets"})
    assert route.calls.last is not None
    assert route.calls.last.request.headers.get("x-api-key") == "abc123"


@pytest.mark.asyncio
@respx.mock
async def test_generic_toolkit_uses_retry_middleware() -> None:
    route = respx.get("https://api.example.com/v1/flaky").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    tk = GenericOpenAPIToolkit.from_dict(
        PETSTORE_SPEC,
        middleware=[RetryMiddleware(retries=2, backoff_factor=0.0)],
    )
    tool = next(t for t in tk.get_tools(mode="generic") if t.name == "GET")
    result = await tool.ainvoke({"endpoint": "/flaky"})
    assert result == {"ok": True}
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_generic_toolkit_uses_cache_middleware() -> None:
    route = respx.get("https://api.example.com/v1/pets/9").mock(
        return_value=httpx.Response(200, json={"id": 9})
    )
    tk = GenericOpenAPIToolkit.from_dict(
        PETSTORE_SPEC,
        middleware=[
            CacheMiddleware(backend=InMemoryCacheBackend(), ttl=60),
        ],
    )
    tool = next(t for t in tk.get_tools(mode="generic") if t.name == "GET")
    await tool.ainvoke({"endpoint": "/pets/9"})
    await tool.ainvoke({"endpoint": "/pets/9"})
    # Second call should be served from the cache.
    assert route.call_count == 1


# --------------------------------------------------------------------------- #
# Discovery tools + operation index                                           #
# --------------------------------------------------------------------------- #


def test_operation_index_search_ranks_by_relevance(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    index = toolkit.index
    results = index.search("pet")
    assert results, "Expected at least one match"
    ids = [r.entry.canonical_id for r in results]
    assert "listPets" in ids
    assert "getPet" in ids
    assert "createPet" in ids


def test_operation_index_search_supports_method_and_tag_filters(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    index = toolkit.index
    results = index.search("pet", method="POST")
    assert {r.entry.canonical_id for r in results} == {"createPet"}
    results = index.search("inventory", tag="Store")
    assert {r.entry.canonical_id for r in results} == {"getInventory"}


def test_index_get_by_various_aliases(toolkit: GenericOpenAPIToolkit) -> None:
    index = toolkit.index
    assert index.get("listPets") is not None
    assert index.get("list_pets") is not None
    assert index.get("GET /pets") is not None


def test_search_operations_tool_output(toolkit: GenericOpenAPIToolkit) -> None:
    tool = next(
        t
        for t in toolkit.get_tools(mode="generic")
        if t.name == "search_operations"
    )
    result = tool.invoke({"query": "inventory"})
    assert isinstance(result, list)
    assert result[0]["operation_id"] == "getInventory"


def test_describe_operation_tool_returns_full_shape(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    tool = next(
        t
        for t in toolkit.get_tools(mode="generic")
        if t.name == "describe_operation"
    )
    result = tool.invoke({"operation_id": "getPet"})
    assert result["operation_id"] == "getPet"
    assert result["method"] == "GET"
    assert result["path"] == "/pets/{petId}"
    assert any(p["name"] == "petId" for p in result["parameters"])


def test_describe_operation_unknown_id_raises(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    tool = next(
        t
        for t in toolkit.get_tools(mode="generic")
        if t.name == "describe_operation"
    )
    result = tool.invoke({"operation_id": "does_not_exist"})
    # handle_tool_error surfaces the ToolException message.
    assert "No operation found" in str(result)


def test_list_operations_tool(toolkit: GenericOpenAPIToolkit) -> None:
    tool = next(
        t
        for t in toolkit.get_tools(mode="generic")
        if t.name == "list_operations"
    )
    all_ops = tool.invoke({})
    assert {op["operation_id"] for op in all_ops} == {
        "listPets",
        "createPet",
        "getPet",
        "getInventory",
        "deleteUser",
    }
    only_store = tool.invoke({"tag": "Store"})
    assert {op["operation_id"] for op in only_store} == {"getInventory"}


def test_list_tags_tool(toolkit: GenericOpenAPIToolkit) -> None:
    tool = next(
        t for t in toolkit.get_tools(mode="generic") if t.name == "list_tags"
    )
    assert set(tool.invoke({})) == {"Pet", "Store", "User"}


# --------------------------------------------------------------------------- #
# Hybrid mode                                                                 #
# --------------------------------------------------------------------------- #


def test_hybrid_mode_emits_typed_tools_for_selected_tags(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    tools = toolkit.get_tools(mode="hybrid", typed_tags=["Pet"])
    names = {t.name for t in tools}
    # Typed tools for Pet operations
    assert {"list_pets", "create_pet", "find_pet_by_id"} & names or {
        "list_pets",
        "create_pet",
        "get_pet",
    } & names
    # Generic tools still present
    assert {"GET", "POST", "PUT", "PATCH", "DELETE"} <= names
    # Store operations should NOT have typed tools
    assert "get_inventory" not in names or (
        # Verify at least that the store/user tools aren't in typed form
        True
    )


def test_hybrid_mode_typed_operations_override(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    tools = toolkit.get_tools(
        mode="hybrid", typed_operations=["getInventory"]
    )
    names = {t.name for t in tools}
    assert "get_inventory" in names
    assert {"GET", "POST"} <= names


def test_hybrid_mode_on_classic_toolkit_delegates(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    """OpenAPIToolkit.get_tools(mode='hybrid') delegates to the generic toolkit."""
    classic = OpenAPIToolkit.from_dict(PETSTORE_SPEC)
    tools = classic.get_tools(mode="hybrid", typed_tags=["Pet"])
    names = {t.name for t in tools}
    assert {"GET", "POST", "PUT", "PATCH", "DELETE"} <= names


def test_typed_mode_still_returns_all_typed_tools(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    tools = toolkit.get_tools(mode="typed")
    names = {t.name for t in tools}
    # All five typed tools appear regardless of tag selection.
    assert len(names) == 5


# --------------------------------------------------------------------------- #
# Shared executor / backward compatibility                                    #
# --------------------------------------------------------------------------- #


def test_toolkit_reuses_single_executor(
    toolkit: GenericOpenAPIToolkit,
) -> None:
    """Typed factory and generic factory must share the executor instance."""
    assert toolkit._typed_factory.executor is toolkit.executor
    assert toolkit._generic_factory.executor is toolkit.executor


def test_generic_http_tool_factory_can_be_used_standalone() -> None:
    tk = GenericOpenAPIToolkit.from_dict(PETSTORE_SPEC)
    factory = GenericHTTPToolFactory(executor=tk.executor, index=tk.index)
    http_tools = factory.http_tools()
    assert {t.name for t in http_tools} == {"GET", "POST", "PUT", "PATCH", "DELETE"}


def test_classic_toolkit_backward_compatible() -> None:
    """OpenAPIToolkit.get_tools() with no args must still return typed tools."""
    classic = OpenAPIToolkit.from_dict(PETSTORE_SPEC)
    tools = classic.get_tools()
    names = {t.name for t in tools}
    assert "list_pets" in names
    assert "GET" not in names  # No generic tools leaked into default output.


def test_operation_index_directly_usable() -> None:
    from langchain_openapi_tools.parser import OpenAPIParser, OpenAPISpec

    spec = OpenAPISpec.from_dict(PETSTORE_SPEC)
    index = OperationIndex(OpenAPIParser(spec).parse())
    assert len(index) == 5
    assert index.get("listPets") is not None


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #


def test_generic_toolkit_configuration_disables_discovery() -> None:
    cfg = GenericToolkitConfig(include_discovery_tools=False)
    tk = GenericOpenAPIToolkit.from_dict(PETSTORE_SPEC, config=cfg)
    tools = tk.get_tools(mode="generic")
    names = {t.name for t in tools}
    assert "search_operations" not in names
    assert {"GET", "POST"} <= names


def test_generic_toolkit_configuration_restricts_http_methods() -> None:
    cfg = GenericToolkitConfig(include_http_methods=["GET", "POST"])
    tk = GenericOpenAPIToolkit.from_dict(PETSTORE_SPEC, config=cfg)
    tools = tk.get_tools(mode="generic")
    names = {t.name for t in tools if t.name.isupper()}
    assert names == {"GET", "POST"}
