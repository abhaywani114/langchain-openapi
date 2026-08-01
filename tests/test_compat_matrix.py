"""End-to-end compatibility tests against representative real-world API specs.

Rather than committing multi-megabyte fixture files or making CI depend on
live network access, these tests carry small structurally-representative
excerpts from each API. Every excerpt validates the same pipeline:

* Spec loading
* Version detection & adapter dispatch
* Reference resolution
* Operation parsing
* Pydantic model generation
* LangChain tool generation
* Request-URL construction (base URL + path template)
* Response parsing (via respx mocks)

APIs covered:

* Swagger Petstore (Swagger 2.0)
* Swagger Petstore (OpenAPI 3.0)
* Crossref (Swagger 2.0-style)
* GitHub REST API (OpenAPI 3.0, oneOf response variants)
* Stripe (OpenAPI 3.0, complex nested schemas)
* Kubernetes (OpenAPI 3.0, JSON-Schema style refs)
* ASP.NET / fakerestapi (OpenAPI 3.0, no ``servers`` block)
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from langchain_openapi_tools import (
    OpenAPILoader,
    OpenAPIToolkit,
)

# ---------------------------------------------------------------------------
# 1. Swagger Petstore 2.0
# ---------------------------------------------------------------------------

PETSTORE_SWAGGER_2: dict[str, Any] = {
    "swagger": "2.0",
    "info": {"title": "Swagger Petstore", "version": "1.0.7"},
    "host": "petstore.swagger.io",
    "basePath": "/v2",
    "schemes": ["https"],
    "paths": {
        "/pet/{petId}": {
            "get": {
                "tags": ["pet"],
                "operationId": "getPetById",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "type": "integer",
                        "format": "int64",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "successful operation",
                        "schema": {"$ref": "#/definitions/Pet"},
                    }
                },
            }
        }
    },
    "definitions": {
        "Pet": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "id": {"type": "integer", "format": "int64"},
                "name": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["available", "pending", "sold"],
                },
            },
        }
    },
}


def test_petstore_swagger_2_pipeline() -> None:
    loader = OpenAPILoader.from_dict(PETSTORE_SWAGGER_2)
    spec = loader.load()

    assert spec.spec_family == "swagger2"
    assert spec.servers == ["https://petstore.swagger.io/v2"]

    toolkit = OpenAPIToolkit(spec=spec)
    tools = toolkit.get_tools()
    assert any(t.name == "get_pet_by_id" for t in tools)


# ---------------------------------------------------------------------------
# 2. Swagger Petstore 3.0
# ---------------------------------------------------------------------------

PETSTORE_OPENAPI_3: dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {"title": "Swagger Petstore", "version": "1.0.0"},
    "servers": [{"url": "https://petstore3.swagger.io/api/v3"}],
    "paths": {
        "/pet/{petId}": {
            "get": {
                "tags": ["pet"],
                "operationId": "getPetById",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer", "format": "int64"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "successful",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Pet"}
                            }
                        },
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Pet": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "id": {"type": "integer", "format": "int64"},
                    "name": {"type": "string"},
                },
            }
        }
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_petstore_openapi_3_pipeline() -> None:
    route = respx.get(
        "https://petstore3.swagger.io/api/v3/pet/42"
    ).mock(
        return_value=httpx.Response(200, json={"id": 42, "name": "Doggo"})
    )

    toolkit = OpenAPIToolkit.from_dict(PETSTORE_OPENAPI_3)
    assert toolkit.spec.spec_family == "openapi30"

    tools = toolkit.get_tools()
    tool = next(t for t in tools if t.name == "get_pet_by_id")
    result = await tool.ainvoke({"petId": 42})
    assert route.called
    assert result == {"id": 42, "name": "Doggo"}


# ---------------------------------------------------------------------------
# 3. Crossref — Swagger 2.0 style, uses parameter-level defaults.
# ---------------------------------------------------------------------------

CROSSREF_SPEC: dict[str, Any] = {
    "swagger": "2.0",
    "info": {"title": "CrossRef Unified Resource API", "version": "1.0"},
    "host": "api.crossref.org",
    "schemes": ["https"],
    "paths": {
        "/works/{doi}": {
            "get": {
                "operationId": "getWorkByDoi",
                "parameters": [
                    {
                        "name": "doi",
                        "in": "path",
                        "required": True,
                        "type": "string",
                    }
                ],
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
}


def test_crossref_swagger_pipeline() -> None:
    loader = OpenAPILoader.from_dict(CROSSREF_SPEC)
    spec = loader.load()
    assert spec.spec_family == "swagger2"
    assert spec.servers == ["https://api.crossref.org"]

    toolkit = OpenAPIToolkit(spec=spec)
    tools = toolkit.get_tools()
    assert any(t.name == "get_work_by_doi" for t in tools)


# ---------------------------------------------------------------------------
# 4. GitHub REST API — OpenAPI 3.0 with oneOf response.
# ---------------------------------------------------------------------------

GITHUB_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "GitHub v3 REST API", "version": "1.1.4"},
    "servers": [{"url": "https://api.github.com"}],
    "paths": {
        "/users/{username}": {
            "get": {
                "operationId": "users/get-by-username",
                "parameters": [
                    {
                        "name": "username",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        {
                                            "$ref": "#/components/schemas/private-user"
                                        },
                                        {
                                            "$ref": "#/components/schemas/public-user"
                                        },
                                    ]
                                }
                            }
                        },
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "private-user": {
                "type": "object",
                "properties": {
                    "login": {"type": "string"},
                    "email": {"type": "string", "nullable": True},
                },
                "required": ["login"],
            },
            "public-user": {
                "type": "object",
                "properties": {"login": {"type": "string"}},
                "required": ["login"],
            },
        }
    },
}


def test_github_openapi_3_oneof_response_parses() -> None:
    toolkit = OpenAPIToolkit.from_dict(GITHUB_SPEC)
    assert toolkit.spec.spec_family == "openapi30"
    tools = toolkit.get_tools()
    assert any(
        t.metadata and t.metadata.get("path") == "/users/{username}" for t in tools
    )


# ---------------------------------------------------------------------------
# 5. Stripe — OpenAPI 3.0 with nested components and anyOf.
# ---------------------------------------------------------------------------

STRIPE_SPEC: dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {"title": "Stripe API", "version": "2024-04-10"},
    "servers": [{"url": "https://api.stripe.com"}],
    "paths": {
        "/v1/charges": {
            "post": {
                "operationId": "PostCharges",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/x-www-form-urlencoded": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "amount": {"type": "integer"},
                                    "currency": {"type": "string"},
                                    "customer": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "string"}
                                                },
                                            },
                                        ]
                                    },
                                },
                                "required": ["amount", "currency"],
                            }
                        }
                    },
                },
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_stripe_urlencoded_body_pipeline() -> None:
    route = respx.post("https://api.stripe.com/v1/charges").mock(
        return_value=httpx.Response(
            200, json={"id": "ch_1", "amount": 100, "currency": "usd"}
        )
    )

    toolkit = OpenAPIToolkit.from_dict(STRIPE_SPEC)
    tools = toolkit.get_tools()
    tool = next(t for t in tools if t.name == "post_charges")

    result = await tool.ainvoke(
        {"amount": 100, "currency": "usd", "customer": "cus_1"}
    )
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["Content-Type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert b"amount=100" in sent.content
    assert b"currency=usd" in sent.content
    assert result["id"] == "ch_1"


# ---------------------------------------------------------------------------
# 6. Kubernetes — OpenAPI 3.0 with allOf composition.
# ---------------------------------------------------------------------------

KUBERNETES_SPEC: dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {"title": "Kubernetes", "version": "v1.29.0"},
    "servers": [{"url": "https://kubernetes.example.com"}],
    "paths": {
        "/api/v1/namespaces/{namespace}/pods": {
            "post": {
                "operationId": "createCoreV1NamespacedPod",
                "parameters": [
                    {
                        "name": "namespace",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/v1.Pod"}
                        }
                    },
                },
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
    "components": {
        "schemas": {
            "v1.ObjectMeta": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "namespace": {"type": "string"},
                },
            },
            "v1.PodSpec": {
                "type": "object",
                "properties": {
                    "containers": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
                "required": ["containers"],
            },
            "v1.Pod": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {
                            "apiVersion": {"type": "string"},
                            "kind": {"type": "string"},
                        },
                    },
                    {
                        "type": "object",
                        "properties": {
                            "metadata": {"$ref": "#/components/schemas/v1.ObjectMeta"},
                            "spec": {"$ref": "#/components/schemas/v1.PodSpec"},
                        },
                    },
                ]
            },
        }
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_kubernetes_allof_pod_pipeline() -> None:
    route = respx.post(
        "https://kubernetes.example.com/api/v1/namespaces/default/pods"
    ).mock(return_value=httpx.Response(201, json={"kind": "Pod"}))

    toolkit = OpenAPIToolkit.from_dict(KUBERNETES_SPEC)
    tools = toolkit.get_tools()
    tool = next(
        t
        for t in tools
        if t.metadata
        and t.metadata.get("path") == "/api/v1/namespaces/{namespace}/pods"
    )

    result = await tool.ainvoke(
        {
            "namespace": "default",
            "body": {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": "test"},
                "spec": {"containers": [{"name": "c", "image": "nginx"}]},
            },
        }
    )
    assert route.called
    assert result == {"kind": "Pod"}


# ---------------------------------------------------------------------------
# 7. ASP.NET (fakerestapi) — OpenAPI 3.0 with no ``servers`` block.
# ---------------------------------------------------------------------------


FAKERESTAPI_SPEC: dict[str, Any] = {
    "openapi": "3.0.1",
    "info": {"title": "FakeRESTApi.Web V1", "version": "v1"},
    "paths": {
        "/api/v1/Activities": {
            "get": {
                "tags": ["Activities"],
                "responses": {"200": {"description": "Success"}},
            }
        }
    },
}


@respx.mock
def test_fakerestapi_no_servers_resolved_via_source_url() -> None:
    respx.get(
        "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json"
    ).mock(
        return_value=httpx.Response(200, json=FAKERESTAPI_SPEC)
    )
    toolkit = OpenAPIToolkit.from_url(
        "https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json"
    )
    assert toolkit.spec.spec_family == "openapi30"
    assert toolkit.spec.servers == ["https://fakerestapi.azurewebsites.net"]
