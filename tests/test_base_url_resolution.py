"""Tests for base-URL / server-URL resolution across the request pipeline.

These tests cover the architectural fix that plumbs the specification's
source URL through the loader → ``OpenAPISpec`` → ``OpenAPIParser`` →
``RequestBuilder`` pipeline so absolute request URLs can always be built,
even when the spec omits the ``servers`` block (OpenAPI 3.x) or the
``host`` field (Swagger 2.0).

The primary real-world driver is
``https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json``, whose
OpenAPI 3.0.1 document contains no ``servers`` block at all.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest
import respx

from langchain_openapi_tools import (
    OpenAPILoader,
    OpenAPIParser,
    OpenAPISpec,
    OpenAPIToolkit,
    SwaggerNormalizer,
)
from langchain_openapi_tools.executor import RequestBuilder

FAKERESTAPI_SPEC_URL = (
    "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json"
)

# Minimal fixture that mirrors the real fakerestapi.azurewebsites.net doc:
# OpenAPI 3.0.1 with NO "servers" block. This is the exact shape that
# broke request execution before the fix.
FAKERESTAPI_SPEC_FIXTURE: dict[str, Any] = {
    "openapi": "3.0.1",
    "info": {"title": "FakeRESTApi.Web V1", "version": "v1"},
    "paths": {
        "/api/v1/Activities": {
            "get": {
                "tags": ["Activities"],
                "responses": {"200": {"description": "Success"}},
            },
            "post": {
                "tags": ["Activities"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Activity"}
                        }
                    }
                },
                "responses": {"200": {"description": "Success"}},
            },
        },
        "/api/v1/Activities/{id}": {
            "get": {
                "tags": ["Activities"],
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer", "format": "int32"},
                    }
                ],
                "responses": {"200": {"description": "Success"}},
            }
        },
    },
    "components": {
        "schemas": {
            "Activity": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "format": "int32"},
                    "title": {"type": "string", "nullable": True},
                    "dueDate": {"type": "string", "format": "date-time"},
                    "completed": {"type": "boolean"},
                },
            }
        }
    },
}


# ---------------------------------------------------------------------------
# 1. servers parsed correctly?
# ---------------------------------------------------------------------------


def test_openapi_3x_servers_parsed_from_spec() -> None:
    """Absolute ``servers`` entries survive the OpenAPISpec round-trip."""
    spec = OpenAPISpec.from_dict(
        {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "servers": [{"url": "https://api.example.com/v1"}],
            "paths": {},
        }
    )
    assert spec.servers == ["https://api.example.com/v1"]


def test_openapi_3x_relative_servers_resolved_against_source_url() -> None:
    """OpenAPI 3.x relative ``servers`` are made absolute via source_url."""
    spec = OpenAPISpec.from_dict(
        {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "servers": [{"url": "/api/v2"}],
            "paths": {},
        },
        source_url="https://example.com/openapi.json",
    )
    assert spec.servers == ["https://example.com/api/v2"]


def test_openapi_3x_missing_servers_falls_back_to_source_origin() -> None:
    """Missing ``servers`` (fakerestapi case) resolves to document origin."""
    spec = OpenAPISpec.from_dict(
        FAKERESTAPI_SPEC_FIXTURE,
        source_url=FAKERESTAPI_SPEC_URL,
    )
    assert spec.servers == ["https://fakerestapi.azurewebsites.net"]


def test_swagger_2_missing_host_falls_back_to_source_url() -> None:
    """Swagger 2.0 without ``host`` derives it from the document URL."""
    raw = {
        "swagger": "2.0",
        "info": {"title": "S", "version": "1"},
        "basePath": "/api",
        "paths": {"/ping": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }
    normalized = SwaggerNormalizer(
        raw, source_url="https://svc.internal.example.com/swagger.json"
    ).normalize()
    assert normalized["servers"] == [
        {"url": "https://svc.internal.example.com/api"}
    ]


def test_swagger_2_explicit_host_wins_over_source_url() -> None:
    """Explicit Swagger 2.0 ``host`` is preferred over the fallback."""
    raw = {
        "swagger": "2.0",
        "info": {"title": "S", "version": "1"},
        "host": "api.example.com",
        "basePath": "/v1",
        "schemes": ["https"],
        "paths": {},
    }
    normalized = SwaggerNormalizer(
        raw, source_url="https://different.example.com/swagger.json"
    ).normalize()
    assert normalized["servers"] == [{"url": "https://api.example.com/v1"}]


# ---------------------------------------------------------------------------
# 2. Stored in OpenAPISpec / 3. Passed to RequestBuilder / 4. Builder gets it
# ---------------------------------------------------------------------------


def test_source_url_stored_on_spec_and_flows_to_toolkit() -> None:
    """OpenAPISpec preserves source_url and toolkit derives base_url from it."""
    spec = OpenAPISpec.from_dict(
        FAKERESTAPI_SPEC_FIXTURE,
        source_url=FAKERESTAPI_SPEC_URL,
    )
    assert spec.source_url == FAKERESTAPI_SPEC_URL
    assert spec.servers, "servers must be non-empty after source_url fallback"

    toolkit = OpenAPIToolkit(spec=spec)
    assert toolkit.executor.base_url == "https://fakerestapi.azurewebsites.net"
    assert (
        toolkit.executor._builder.base_url
        == "https://fakerestapi.azurewebsites.net"
    )


def test_request_builder_produces_absolute_url_for_fakerestapi() -> None:
    """RequestBuilder receives the resolved base URL and builds absolute URLs."""
    spec = OpenAPISpec.from_dict(
        FAKERESTAPI_SPEC_FIXTURE,
        source_url=FAKERESTAPI_SPEC_URL,
    )
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    get_activities = next(
        op
        for op in operations
        if op.path == "/api/v1/Activities" and op.method.value == "GET"
    )
    builder = RequestBuilder(base_url=spec.servers[0])
    built = builder.build(get_activities, arguments={})

    assert built.url == "https://fakerestapi.azurewebsites.net/api/v1/Activities"


def test_request_builder_expands_path_parameters_with_resolved_base() -> None:
    """Path parameters still expand correctly when base_url comes from source_url."""
    spec = OpenAPISpec.from_dict(
        FAKERESTAPI_SPEC_FIXTURE,
        source_url=FAKERESTAPI_SPEC_URL,
    )
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    get_by_id = next(
        op
        for op in operations
        if op.path == "/api/v1/Activities/{id}" and op.method.value == "GET"
    )
    builder = RequestBuilder(base_url=spec.servers[0])
    built = builder.build(get_by_id, arguments={"id": 7})

    assert (
        built.url
        == "https://fakerestapi.azurewebsites.net/api/v1/Activities/7"
    )


# ---------------------------------------------------------------------------
# End-to-end via the loader against the real spec URL (respx-mocked)
# ---------------------------------------------------------------------------


@respx.mock
def test_loader_from_url_pipelines_source_url_into_spec() -> None:
    """Full pipeline: loader remembers URL, spec uses it for base URL resolution."""
    respx.get(FAKERESTAPI_SPEC_URL).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(FAKERESTAPI_SPEC_FIXTURE),
            headers={"content-type": "application/json"},
        )
    )

    loader = OpenAPILoader.from_url(FAKERESTAPI_SPEC_URL)
    spec = loader.load()

    assert spec.source_url == FAKERESTAPI_SPEC_URL
    assert spec.servers == ["https://fakerestapi.azurewebsites.net"]


@pytest.mark.asyncio
@respx.mock
async def test_toolkit_from_url_executes_against_absolute_url() -> None:
    """OpenAPIToolkit.from_url pipes source URL through so requests hit real host."""
    respx.get(FAKERESTAPI_SPEC_URL).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(FAKERESTAPI_SPEC_FIXTURE),
            headers={"content-type": "application/json"},
        )
    )
    api_route = respx.get(
        "https://fakerestapi.azurewebsites.net/api/v1/Activities/1"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"id": 1, "title": "Activity 1", "completed": False},
        )
    )

    toolkit = OpenAPIToolkit.from_url(FAKERESTAPI_SPEC_URL)
    tools = toolkit.get_tools()

    # Pick the "get activity by id" tool without relying on naming details.
    target_tool = next(
        t
        for t in tools
        if getattr(t, "metadata", None)
        and t.metadata.get("path") == "/api/v1/Activities/{id}"
        and t.metadata.get("method") == "GET"
    )

    result = await target_tool.ainvoke({"id": 1})

    assert api_route.called
    assert api_route.calls.last.request.url.host == "fakerestapi.azurewebsites.net"
    assert result == {"id": 1, "title": "Activity 1", "completed": False}


# ---------------------------------------------------------------------------
# Optional live integration test — hits the real fakerestapi endpoint.
# Skipped by default; enable with RUN_LIVE_FAKERESTAPI=1.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_FAKERESTAPI") != "1",
    reason="Live network test; set RUN_LIVE_FAKERESTAPI=1 to enable",
)
async def test_live_fakerestapi_spec_end_to_end() -> None:
    """Verify the fix against the real fakerestapi.azurewebsites.net service."""
    toolkit = OpenAPIToolkit.from_url(FAKERESTAPI_SPEC_URL)

    # Post-fix: spec.servers must contain an absolute URL derived from source_url.
    assert toolkit.spec.servers
    assert toolkit.spec.servers[0].startswith("https://")

    tools = toolkit.get_tools()
    # Find the "list activities" tool by its metadata rather than name.
    list_tool = next(
        t
        for t in tools
        if getattr(t, "metadata", None)
        and t.metadata.get("path") == "/api/v1/Activities"
        and t.metadata.get("method") == "GET"
    )

    result = await list_tool.ainvoke({})
    assert isinstance(result, list)
    assert len(result) > 0
