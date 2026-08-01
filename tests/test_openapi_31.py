"""Tests for OpenAPI 3.1 / JSON Schema 2020-12 support.

Covers:
* Union types via ``type: [X, "null"]``.
* ``oneOf`` / ``anyOf`` compositions → Pydantic ``Union`` annotations.
* ``allOf`` composition → merged Pydantic model.
* ``const`` acceptance.
* ``readOnly`` / ``writeOnly`` / ``deprecated`` propagation.
"""

from __future__ import annotations

from typing import Union, get_args, get_origin

from langchain_openapi_tools import (
    OpenAPIParser,
    OpenAPISpec,
    SchemaConverter,
)


def _make_spec(schemas: dict[str, dict], body_schema: dict) -> OpenAPISpec:
    return OpenAPISpec.from_dict(
        {
            "openapi": "3.1.0",
            "info": {"title": "T", "version": "1"},
            "servers": [{"url": "https://api.example.com"}],
            "components": {"schemas": schemas},
            "paths": {
                "/things": {
                    "post": {
                        "operationId": "createThing",
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": body_schema}},
                        },
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
    )


def test_openapi_31_union_type_null_marks_nullable() -> None:
    spec = _make_spec(
        {},
        {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
            },
        },
    )
    parser = OpenAPIParser(spec)
    op = parser.parse()[0]
    assert op.request_body is not None
    media = op.request_body.content["application/json"]
    assert media.schema is not None
    assert media.schema.properties is not None
    name_schema = media.schema.properties["name"]
    assert name_schema.nullable is True
    assert name_schema.type in ("string",) or name_schema.type.value == "string"  # type: ignore[union-attr]


def test_openapi_31_union_type_two_non_null_produces_union_annotation() -> None:
    spec = _make_spec(
        {},
        {
            "type": "object",
            "properties": {"code": {"type": ["string", "integer"]}},
            "required": ["code"],
        },
    )
    parser = OpenAPIParser(spec)
    op = parser.parse()[0]
    model = SchemaConverter().to_pydantic(op)
    ann = model.model_fields["code"].annotation
    origin = get_origin(ann)
    # Union[str, int] — accept either the typing.Union origin or types.UnionType.
    assert origin in (Union, type(int | str))
    assert set(get_args(ann)) == {str, int}


def test_openapi_31_oneof_produces_union_annotation() -> None:
    spec = _make_spec(
        {
            "Cat": {"type": "object", "properties": {"meow": {"type": "boolean"}}},
            "Dog": {"type": "object", "properties": {"bark": {"type": "boolean"}}},
        },
        {
            "oneOf": [
                {"$ref": "#/components/schemas/Cat"},
                {"$ref": "#/components/schemas/Dog"},
            ]
        },
    )
    parser = OpenAPIParser(spec)
    op = parser.parse()[0]
    model = SchemaConverter().to_pydantic(op)
    body_ann = model.model_fields["body"].annotation
    # Non-required body wraps the union in Optional[...] → Union[..., None].
    args = get_args(body_ann)
    assert len(args) >= 2


def test_openapi_31_anyof_produces_union_annotation() -> None:
    spec = _make_spec(
        {},
        {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
            ]
        },
    )
    parser = OpenAPIParser(spec)
    op = parser.parse()[0]
    model = SchemaConverter().to_pydantic(op)
    body_ann = model.model_fields["body"].annotation
    # Should include str and int (Optional adds None).
    args = set(get_args(body_ann))
    assert str in args and int in args


def test_openapi_31_allof_merges_into_single_model() -> None:
    spec = _make_spec(
        {
            "Base": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
            "Extension": {
                "type": "object",
                "properties": {"note": {"type": "string"}},
            },
        },
        {
            "allOf": [
                {"$ref": "#/components/schemas/Base"},
                {"$ref": "#/components/schemas/Extension"},
            ]
        },
    )
    parser = OpenAPIParser(spec)
    op = parser.parse()[0]
    model = SchemaConverter().to_pydantic(op)
    # allOf merged into a top-level object; its properties are flattened
    # as separate fields on the request model (id + note).
    assert "id" in model.model_fields
    assert "note" in model.model_fields


def test_openapi_31_const_captured_on_schema() -> None:
    spec = _make_spec(
        {},
        {
            "type": "object",
            "properties": {"kind": {"const": "user"}},
        },
    )
    parser = OpenAPIParser(spec)
    op = parser.parse()[0]
    body_schema = op.request_body.content["application/json"].schema  # type: ignore[union-attr]
    assert body_schema is not None
    assert body_schema.properties is not None
    assert body_schema.properties["kind"].const == "user"


def test_openapi_31_readonly_writeonly_deprecated_captured() -> None:
    spec = _make_spec(
        {},
        {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "readOnly": True},
                "password": {"type": "string", "writeOnly": True},
                "legacy": {"type": "string", "deprecated": True},
            },
        },
    )
    parser = OpenAPIParser(spec)
    op = parser.parse()[0]
    body_schema = op.request_body.content["application/json"].schema  # type: ignore[union-attr]
    assert body_schema is not None
    props = body_schema.properties or {}
    assert props["id"].read_only is True
    assert props["password"].write_only is True
    assert props["legacy"].deprecated is True
