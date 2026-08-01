"""Tests for Swagger 2.0 normalization and compatibility."""

from typing import Any

from langchain_openapi import (
    OpenAPILoader,
    OpenAPISpec,
    OpenAPIToolkit,
    SwaggerNormalizer,
)


def test_swagger_normalizer_basic() -> None:
    """Test basic Swagger 2.0 to OpenAPI 3.0 conversion."""
    raw_swagger: dict[str, Any] = {
        "swagger": "2.0",
        "info": {"title": "Petstore Swagger", "version": "1.0.0"},
        "host": "petstore.swagger.io",
        "basePath": "/v2",
        "schemes": ["https"],
        "definitions": {
            "Pet": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "format": "int64"},
                    "name": {"type": "string"},
                },
                "required": ["name"],
            }
        },
        "parameters": {
            "PetParam": {
                "name": "petId",
                "in": "path",
                "required": True,
                "type": "integer",
                "format": "int64",
            }
        },
        "responses": {
            "NotFound": {
                "description": "Pet not found",
            }
        },
        "securityDefinitions": {
            "api_key": {"type": "apiKey", "name": "api_key", "in": "header"},
            "basic_auth": {"type": "basic"},
            "oauth_auth": {
                "type": "oauth2",
                "flow": "implicit",
                "authorizationUrl": "https://example.com/oauth/dialog",
                "scopes": {"read:pets": "read pets"},
            },
        },
        "paths": {
            "/pet/{petId}": {
                "get": {
                    "summary": "Find pet by ID",
                    "operationId": "getPetById",
                    "produces": ["application/json"],
                    "parameters": [{"$ref": "#/parameters/PetParam"}],
                    "responses": {
                        "200": {
                            "description": "successful operation",
                            "schema": {"$ref": "#/definitions/Pet"},
                        },
                        "404": {"$ref": "#/responses/NotFound"},
                    },
                }
            },
            "/pet": {
                "post": {
                    "summary": "Add a new pet",
                    "operationId": "addPet",
                    "consumes": ["application/json"],
                    "parameters": [
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {"$ref": "#/definitions/Pet"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Pet added"},
                    },
                }
            },
            "/pet/uploadImage": {
                "post": {
                    "summary": "Upload image",
                    "operationId": "uploadFile",
                    "consumes": ["multipart/form-data"],
                    "parameters": [
                        {
                            "name": "additionalMetadata",
                            "in": "formData",
                            "type": "string",
                        },
                        {
                            "name": "file",
                            "in": "formData",
                            "type": "file",
                            "required": True,
                        },
                    ],
                    "responses": {
                        "200": {"description": "Image uploaded"},
                    },
                }
            },
        },
    }

    normalizer = SwaggerNormalizer(raw_swagger)
    normalized = normalizer.normalize()

    assert normalized["openapi"] == "3.0.3"
    assert normalized["servers"] == [{"url": "https://petstore.swagger.io/v2"}]
    assert "Pet" in normalized["components"]["schemas"]
    assert "PetParam" in normalized["components"]["parameters"]
    assert "NotFound" in normalized["components"]["responses"]
    assert "api_key" in normalized["components"]["securitySchemes"]
    assert normalized["components"]["securitySchemes"]["basic_auth"] == {
        "type": "http",
        "scheme": "basic",
    }

    # Reference rewriting check
    get_op = normalized["paths"]["/pet/{petId}"]["get"]
    assert get_op["parameters"][0]["$ref"] == "#/components/parameters/PetParam"
    assert (
        get_op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Pet"
    )

    # Body param check
    post_op = normalized["paths"]["/pet"]["post"]
    assert "requestBody" in post_op
    assert (
        post_op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Pet"
    )

    # FormData check
    upload_op = normalized["paths"]["/pet/uploadImage"]["post"]
    assert "requestBody" in upload_op
    form_schema = upload_op["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert form_schema["properties"]["file"]["format"] == "binary"
    assert form_schema["required"] == ["file"]


def test_swagger_toolkit_integration() -> None:
    """Test generating LangChain tools from a Swagger 2.0 spec dictionary."""
    raw_swagger: dict[str, Any] = {
        "swagger": "2.0",
        "info": {"title": "Sample Swagger API", "version": "1.0.0"},
        "host": "api.example.com",
        "basePath": "/v1",
        "paths": {
            "/users": {
                "get": {
                    "summary": "List users",
                    "operationId": "listUsers",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "type": "integer",
                            "default": 10,
                        }
                    ],
                    "responses": {
                        "200": {"description": "User list"},
                    },
                }
            }
        },
    }

    spec = OpenAPISpec.from_dict(raw_swagger)
    assert spec.title == "Sample Swagger API"
    assert spec.servers == ["https://api.example.com/v1"]

    toolkit = OpenAPIToolkit.from_dict(raw_swagger)
    tools = toolkit.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "list_users"


def test_swagger_loader_file_integration(tmp_path: Any) -> None:
    """Test loading a Swagger 2.0 spec from a local JSON file."""
    swagger_file = tmp_path / "swagger.json"
    swagger_content = """{
        "swagger": "2.0",
        "info": {"title": "File Swagger API", "version": "2.0.0"},
        "host": "localhost:8000",
        "schemes": ["http"],
        "paths": {
            "/status": {
                "get": {
                    "summary": "Check status",
                    "operationId": "checkStatus",
                    "responses": {"200": {"description": "OK"}}
                }
            }
        }
    }"""
    swagger_file.write_text(swagger_content, encoding="utf-8")

    loader = OpenAPILoader.from_file(swagger_file)
    spec = loader.load()

    assert spec.title == "File Swagger API"
    assert spec.servers == ["http://localhost:8000"]
