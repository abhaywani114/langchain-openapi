"""Tests for SchemaConverter and PydanticFactory."""

from enum import Enum
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from langchain_openapi import (
    DataType,
    HTTPMethod,
    MediaType,
    OpenAPILoader,
    OpenAPIParser,
    Operation,
    Parameter,
    ParameterLocation,
    RequestBody,
    Schema,
    SchemaConverter,
)


def test_primitive_types_and_defaults() -> None:
    """Test primitive type conversion (string, integer, float, boolean) and defaults."""
    op = Operation(
        name="testPrimitives",
        method=HTTPMethod.GET,
        path="/test",
        parameters=[
            Parameter(
                name="query",
                location=ParameterLocation.QUERY,
                required=True,
                description="Search text",
                schema=Schema(type=DataType.STRING),
            ),
            Parameter(
                name="count",
                location=ParameterLocation.QUERY,
                required=False,
                default=10,
                description="Item count",
                schema=Schema(type=DataType.INTEGER),
            ),
            Parameter(
                name="ratio",
                location=ParameterLocation.QUERY,
                required=False,
                schema=Schema(type=DataType.NUMBER),
            ),
            Parameter(
                name="active",
                location=ParameterLocation.QUERY,
                required=False,
                schema=Schema(type=DataType.BOOLEAN),
            ),
        ],
    )

    converter = SchemaConverter()
    Model = converter.to_pydantic(op)

    assert issubclass(Model, BaseModel)
    assert Model.__name__ == "TestPrimitivesInput"

    # Instantiate with required field
    instance = Model(query="hello", ratio=1.5, active=True)
    assert instance.query == "hello"  # type: ignore[attr-defined]
    assert instance.count == 10  # type: ignore[attr-defined]
    assert instance.ratio == 1.5  # type: ignore[attr-defined]
    assert instance.active is True  # type: ignore[attr-defined]


def test_enum_generation() -> None:
    """Test dynamic Enum creation and field validation."""
    op = Operation(
        name="sortItems",
        method=HTTPMethod.GET,
        path="/items",
        parameters=[
            Parameter(
                name="sort",
                location=ParameterLocation.QUERY,
                required=True,
                schema=Schema(type=DataType.STRING, enum=["asc", "desc"]),
            )
        ],
    )

    converter = SchemaConverter()
    Model = converter.to_pydantic(op)

    instance = Model(sort="asc")
    assert instance.sort == "asc"  # type: ignore[attr-defined]
    assert isinstance(instance.sort, Enum)  # type: ignore[attr-defined]

    # Test validation error on invalid enum value
    with pytest.raises(ValidationError):
        Model(sort="invalid_direction")


def test_array_schema() -> None:
    """Test array parameter type conversion (list[str])."""
    op = Operation(
        name="filterTags",
        method=HTTPMethod.GET,
        path="/tags",
        parameters=[
            Parameter(
                name="tags",
                location=ParameterLocation.QUERY,
                required=False,
                schema=Schema(
                    type=DataType.ARRAY,
                    items=Schema(type=DataType.STRING),
                ),
            )
        ],
    )

    converter = SchemaConverter()
    Model = converter.to_pydantic(op)

    instance = Model(tags=["python", "openapi"])
    assert instance.tags == ["python", "openapi"]  # type: ignore[attr-defined]

    with pytest.raises(ValidationError):
        Model(tags="not_a_list")


def test_nested_object_schema() -> None:
    """Test nested object model creation."""
    op = Operation(
        name="createUser",
        method=HTTPMethod.POST,
        path="/users",
        request_body=RequestBody(
            required=True,
            content={
                "application/json": MediaType(
                    content_type="application/json",
                    schema=Schema(
                        type=DataType.OBJECT,
                        required=["name", "address"],
                        properties={
                            "name": Schema(type=DataType.STRING),
                            "address": Schema(
                                type=DataType.OBJECT,
                                required=["city"],
                                properties={
                                    "city": Schema(type=DataType.STRING),
                                    "zip": Schema(type=DataType.STRING),
                                },
                            ),
                        },
                    ),
                )
            },
        ),
    )

    converter = SchemaConverter()
    Model = converter.to_pydantic(op)

    assert Model.__name__ == "CreateUserInput"
    instance = Model(name="Alice", address={"city": "Seattle", "zip": "98101"})
    assert instance.name == "Alice"  # type: ignore[attr-defined]
    assert instance.address.city == "Seattle"  # type: ignore[attr-defined]
    assert instance.address.zip == "98101"  # type: ignore[attr-defined]

    with pytest.raises(ValidationError):
        # Missing required nested field 'city'
        Model(name="Alice", address={"zip": "98101"})


def test_full_spec_conversion() -> None:
    """Test end-to-end load -> parse -> convert pipeline using OpenAPI spec dict."""
    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Search API", "version": "1.0.0"},
        "paths": {
            "/search": {
                "get": {
                    "operationId": "searchWorks",
                    "parameters": [
                        {
                            "name": "query",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Search query text",
                        },
                        {
                            "name": "rows",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "responses": {"200": {"description": "Success"}},
                }
            }
        },
    }

    loader = OpenAPILoader.from_dict(spec_dict)
    spec = loader.load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()

    converter = SchemaConverter()
    Model = converter.to_pydantic(operations[0])

    assert Model.__name__ == "SearchWorksInput"
    inst = Model(query="LangChain", rows=5)
    assert inst.query == "LangChain"  # type: ignore[attr-defined]
    assert inst.rows == 5  # type: ignore[attr-defined]


def test_validation_errors() -> None:
    """Test Pydantic validation rejects invalid types automatically."""
    op = Operation(
        name="updateAge",
        method=HTTPMethod.PUT,
        path="/age",
        parameters=[
            Parameter(
                name="age",
                location=ParameterLocation.QUERY,
                required=True,
                schema=Schema(type=DataType.INTEGER),
            )
        ],
    )

    converter = SchemaConverter()
    Model = converter.to_pydantic(op)

    with pytest.raises(ValidationError):
        Model(age="not_an_int")

    with pytest.raises(ValidationError):
        # Missing required parameter
        Model()
