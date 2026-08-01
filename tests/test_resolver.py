"""Tests for ReferenceResolver."""

import pytest

from langchain_openapi_tools import InvalidSpecError, ReferenceResolver


def test_resolve_simple_local_ref() -> None:
    """Test resolving a basic #/components/schemas/Pet reference."""
    raw_spec = {
        "openapi": "3.0.3",
        "components": {
            "schemas": {
                "Pet": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        },
        "paths": {
            "/pets": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Pet"}
                            }
                        }
                    }
                }
            }
        },
    }

    resolver = ReferenceResolver(raw_spec)
    paths_dict = raw_spec["paths"]
    assert isinstance(paths_dict, dict)
    resolved = resolver.resolve(paths_dict["/pets"])

    post_schema = resolved["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert post_schema["type"] == "object"
    assert post_schema["properties"]["name"]["type"] == "string"


def test_resolve_nested_and_transitive_refs() -> None:
    """Test resolving nested and transitive $ref pointers."""
    raw_spec = {
        "components": {
            "schemas": {
                "Category": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                },
                "Pet": {
                    "type": "object",
                    "properties": {
                        "category": {"$ref": "#/components/schemas/Category"}
                    },
                },
                "PetAlias": {"$ref": "#/components/schemas/Pet"},
            }
        }
    }

    resolver = ReferenceResolver(raw_spec)
    resolved = resolver.resolve(raw_spec["components"]["schemas"]["PetAlias"])

    assert resolved["type"] == "object"
    assert resolved["properties"]["category"]["type"] == "object"
    assert resolved["properties"]["category"]["properties"]["id"]["type"] == "integer"


def test_resolve_unsupported_remote_ref() -> None:
    """Test that remote references (HTTP or file) raise InvalidSpecError."""
    raw_spec = {"$ref": "https://example.com/schemas/Pet.json"}
    resolver = ReferenceResolver(raw_spec)

    with pytest.raises(InvalidSpecError, match="Unsupported reference format"):
        resolver.resolve(raw_spec)


def test_resolve_missing_pointer_raises_error() -> None:
    """Test that resolving a non-existent $ref pointer raises InvalidSpecError."""
    raw_spec = {
        "components": {"schemas": {}},
        "$ref": "#/components/schemas/NonExistent",
    }
    resolver = ReferenceResolver(raw_spec)

    with pytest.raises(InvalidSpecError, match="key 'NonExistent' not found"):
        resolver.resolve(raw_spec)


def test_resolve_circular_ref() -> None:
    """Test that circular references are handled safely without infinite loops."""
    raw_spec = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}},
                }
            }
        }
    }

    resolver = ReferenceResolver(raw_spec)
    resolved = resolver.resolve(raw_spec["components"]["schemas"]["Node"])

    assert resolved["type"] == "object"
    assert "child" in resolved["properties"]
