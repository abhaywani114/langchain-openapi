"""Tests for OpenAPIParser."""

from typing import Any

from langchain_openapi import (
    DataType,
    HTTPMethod,
    OpenAPILoader,
    OpenAPIParser,
    ParameterLocation,
    generate_fallback_operation_name,
)

SAMPLE_OPENAPI_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Test Store API", "version": "1.0.0"},
    "components": {
        "schemas": {
            "Pet": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "integer", "format": "int64"},
                    "name": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "Error": {
                "type": "object",
                "properties": {
                    "code": {"type": "integer"},
                    "message": {"type": "string"},
                },
            },
        },
        "parameters": {
            "PetIdParam": {
                "name": "petId",
                "in": "path",
                "required": True,
                "description": "ID of pet to fetch",
                "schema": {"type": "integer"},
            }
        },
    },
    "paths": {
        "/pets": {
            "get": {
                "summary": "List all pets",
                "description": "Returns a list of pets with pagination",
                "tags": ["pets"],
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "description": "Max items to return",
                        "schema": {"type": "integer", "default": 20},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "A list of pets",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Pet"},
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "operationId": "createPet",
                "summary": "Create a pet",
                "tags": ["pets"],
                "requestBody": {
                    "required": True,
                    "description": "Pet object to create",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Pet"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Pet created successfully",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Pet"}
                            }
                        },
                    }
                },
            },
        },
        "/pets/{petId}": {
            "parameters": [{"$ref": "#/components/parameters/PetIdParam"}],
            "get": {
                "summary": "Get pet by ID",
                "responses": {
                    "200": {
                        "description": "Pet details",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Pet"}
                            }
                        },
                    },
                    "404": {
                        "description": "Pet not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
    },
}


def test_fallback_operation_name_generation() -> None:
    """Test fallback operation name generator logic."""
    assert generate_fallback_operation_name("GET", "/users") == "get_users"
    assert generate_fallback_operation_name("GET", "/users/{id}") == "get_users_by_id"
    assert (
        generate_fallback_operation_name("POST", "/pets/{petId}/owners")
        == "post_pets_by_pet_id_owners"
    )
    assert generate_fallback_operation_name("GET", "/") == "get_root"


def test_parse_operations_count_and_methods() -> None:
    """Test parsing multiple endpoints and HTTP methods."""
    loader = OpenAPILoader.from_dict(SAMPLE_OPENAPI_SPEC)
    spec = loader.load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    assert len(operations) == 3

    op_map = {(op.method.value, op.path): op for op in operations}
    assert ("GET", "/pets") in op_map
    assert ("POST", "/pets") in op_map
    assert ("GET", "/pets/{petId}") in op_map


def test_parse_operation_without_operation_id() -> None:
    """Test operation without operationId falls back to generated name."""
    loader = OpenAPILoader.from_dict(SAMPLE_OPENAPI_SPEC)
    spec = loader.load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    get_pets_op = next(
        op for op in operations if op.method == HTTPMethod.GET and op.path == "/pets"
    )
    assert get_pets_op.operation_id is None
    assert get_pets_op.name == "get_pets"
    assert get_pets_op.summary == "List all pets"
    assert get_pets_op.tags == ["pets"]


def test_parse_explicit_operation_id() -> None:
    """Test operation with explicit operationId preserves it."""
    loader = OpenAPILoader.from_dict(SAMPLE_OPENAPI_SPEC)
    spec = loader.load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    post_pets_op = next(
        op for op in operations if op.method == HTTPMethod.POST and op.path == "/pets"
    )
    assert post_pets_op.operation_id == "createPet"
    assert post_pets_op.name == "createPet"


def test_parse_query_and_path_parameters() -> None:
    """Test parsing query parameters and path parameter references."""
    loader = OpenAPILoader.from_dict(SAMPLE_OPENAPI_SPEC)
    spec = loader.load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    get_pets_op = next(
        op for op in operations if op.method == HTTPMethod.GET and op.path == "/pets"
    )
    assert len(get_pets_op.parameters) == 1
    param = get_pets_op.parameters[0]
    assert param.name == "limit"
    assert param.location == ParameterLocation.QUERY
    assert param.required is False
    assert param.default == 20
    assert param.schema is not None
    assert param.schema.type == DataType.INTEGER

    get_by_id_op = next(op for op in operations if op.path == "/pets/{petId}")
    assert len(get_by_id_op.parameters) == 1
    path_param = get_by_id_op.parameters[0]
    assert path_param.name == "petId"
    assert path_param.location == ParameterLocation.PATH
    assert path_param.required is True


def test_parse_request_body_and_schemas() -> None:
    """Test request body parsing and resolved object schema properties."""
    loader = OpenAPILoader.from_dict(SAMPLE_OPENAPI_SPEC)
    spec = loader.load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    post_op = next(op for op in operations if op.method == HTTPMethod.POST)
    assert post_op.request_body is not None
    assert post_op.request_body.required is True
    assert "application/json" in post_op.request_body.content

    media_type = post_op.request_body.content["application/json"]
    schema = media_type.schema
    assert schema is not None
    assert schema.type == DataType.OBJECT
    assert schema.required == ["id", "name"]
    assert schema.properties is not None
    assert "id" in schema.properties
    assert "name" in schema.properties
    assert "tags" in schema.properties

    # Check array schema in object property
    tags_schema = schema.properties["tags"]
    assert tags_schema is not None
    assert tags_schema.type == DataType.ARRAY
    assert tags_schema.items is not None
    assert tags_schema.items.type == DataType.STRING


def test_parse_responses() -> None:
    """Test response status codes and media type mapping."""
    loader = OpenAPILoader.from_dict(SAMPLE_OPENAPI_SPEC)
    spec = loader.load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    get_by_id_op = next(op for op in operations if op.path == "/pets/{petId}")
    assert "200" in get_by_id_op.responses
    assert "404" in get_by_id_op.responses

    resp_200 = get_by_id_op.responses["200"]
    assert resp_200.description == "Pet details"
    assert "application/json" in resp_200.content

    resp_404 = get_by_id_op.responses["404"]
    assert resp_404.description == "Pet not found"
