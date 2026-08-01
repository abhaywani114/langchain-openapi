"""Tests for OpenAPILoader and OpenAPISpec."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import Response

from langchain_openapi import (
    InvalidSpecError,
    OpenAPILoader,
    OpenAPISpec,
    SpecLoadError,
    UnsupportedVersionError,
)

VALID_SPEC_DICT: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {
        "title": "Sample Petstore API",
        "description": "A sample API for testing",
        "version": "1.0.0",
    },
    "servers": [{"url": "https://api.example.com/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "summary": "List all pets",
                "responses": {"200": {"description": "Successful response"}},
            }
        }
    },
}

VALID_YAML_CONTENT = """
openapi: 3.1.0
info:
  title: Sample YAML API
  description: YAML spec test
servers:
  - url: https://yaml.example.com
paths:
  /users:
    get:
      summary: List users
"""


def test_load_dict() -> None:
    """Test loading an OpenAPI spec directly from a Python dictionary."""
    loader = OpenAPILoader.from_dict(VALID_SPEC_DICT)
    spec = loader.load()

    assert isinstance(spec, OpenAPISpec)
    assert spec.version == "3.0.3"
    assert spec.title == "Sample Petstore API"
    assert spec.description == "A sample API for testing"
    assert spec.servers == ["https://api.example.com/v1"]
    assert "/pets" in spec.paths
    assert spec.raw == VALID_SPEC_DICT
    assert repr(spec) == "<OpenAPISpec title='Sample Petstore API' version='3.0.3'>"


def test_load_json_file(tmp_path: Path) -> None:
    """Test loading an OpenAPI spec from a local JSON file."""
    file_path = tmp_path / "spec.json"
    file_path.write_text(json.dumps(VALID_SPEC_DICT), encoding="utf-8")

    loader = OpenAPILoader.from_file(file_path)
    spec = loader.load()

    assert spec.title == "Sample Petstore API"
    assert spec.version == "3.0.3"
    assert "/pets" in spec.paths


def test_load_yaml_file(tmp_path: Path) -> None:
    """Test loading an OpenAPI spec from a local YAML file."""
    file_path = tmp_path / "spec.yaml"
    file_path.write_text(VALID_YAML_CONTENT, encoding="utf-8")

    loader = OpenAPILoader.from_file(file_path)
    spec = loader.load()

    assert spec.title == "Sample YAML API"
    assert spec.version == "3.1.0"
    assert spec.servers == ["https://yaml.example.com"]
    assert "/users" in spec.paths


@respx.mock
def test_load_url_json() -> None:
    """Test loading an OpenAPI spec from a remote URL serving JSON."""
    url = "https://api.example.com/openapi.json"
    respx.get(url).mock(return_value=Response(200, json=VALID_SPEC_DICT))

    loader = OpenAPILoader.from_url(url, headers={"X-Test": "Header"})
    spec = loader.load()

    assert spec.title == "Sample Petstore API"
    assert spec.version == "3.0.3"


@respx.mock
def test_load_url_yaml() -> None:
    """Test loading an OpenAPI spec from a remote URL serving YAML."""
    url = "https://api.example.com/openapi.yaml"
    respx.get(url).mock(return_value=Response(200, text=VALID_YAML_CONTENT))

    loader = OpenAPILoader.from_url(url)
    spec = loader.load()

    assert spec.title == "Sample YAML API"
    assert spec.version == "3.1.0"


@respx.mock
def test_load_url_http_error() -> None:
    """Test loading from a URL that returns a 404 HTTP error."""
    url = "https://api.example.com/notfound.json"
    respx.get(url).mock(return_value=Response(404))

    loader = OpenAPILoader.from_url(url)
    with pytest.raises(SpecLoadError, match="Failed to fetch specification from URL"):
        loader.load()


def test_invalid_file_path(tmp_path: Path) -> None:
    """Test loading from a non-existent file path."""
    non_existent = tmp_path / "does_not_exist.json"
    loader = OpenAPILoader.from_file(non_existent)

    with pytest.raises(SpecLoadError, match="Specification file not found"):
        loader.load()


def test_invalid_json_content(tmp_path: Path) -> None:
    """Test loading a file with invalid JSON syntax."""
    file_path = tmp_path / "invalid.json"
    file_path.write_text("{ invalid json structure: ", encoding="utf-8")

    loader = OpenAPILoader.from_file(file_path)
    with pytest.raises(SpecLoadError, match="Failed to parse specification content"):
        loader.load()


def test_invalid_yaml_content(tmp_path: Path) -> None:
    """Test loading a file with invalid YAML syntax."""
    file_path = tmp_path / "invalid.yaml"
    file_path.write_text(":\n  - : : : invalid yaml syntax", encoding="utf-8")

    loader = OpenAPILoader.from_file(file_path)
    with pytest.raises(SpecLoadError, match="Failed to parse specification content"):
        loader.load()


def test_non_dict_json_content(tmp_path: Path) -> None:
    """Test loading a JSON file containing a top-level list instead of a dict."""
    file_path = tmp_path / "array.json"
    file_path.write_text("[1, 2, 3]", encoding="utf-8")

    loader = OpenAPILoader.from_file(file_path)
    pattern = "Specification content must be a JSON object"
    with pytest.raises(InvalidSpecError, match=pattern):
        loader.load()


def test_missing_openapi_field() -> None:
    """Test loading a spec dictionary missing the required 'openapi' field."""
    invalid_dict = {"info": {"title": "No Version"}, "paths": {}}
    loader = OpenAPILoader.from_dict(invalid_dict)

    with pytest.raises(InvalidSpecError, match="missing required field: 'openapi'"):
        loader.load()


def test_missing_paths_field() -> None:
    """Test loading a spec dictionary missing the required 'paths' field."""
    invalid_dict = {"openapi": "3.0.0", "info": {"title": "No Paths"}}
    loader = OpenAPILoader.from_dict(invalid_dict)

    with pytest.raises(InvalidSpecError, match="missing required field: 'paths'"):
        loader.load()


def test_paths_not_a_dict() -> None:
    """Test loading a spec dictionary where 'paths' is not a dict."""
    invalid_dict = {"openapi": "3.0.0", "paths": ["not", "a", "dict"]}
    loader = OpenAPILoader.from_dict(invalid_dict)

    with pytest.raises(InvalidSpecError, match="'paths' field must be a dictionary"):
        loader.load()


def test_swagger_2_0_supported() -> None:
    """Test loading a Swagger 2.0 specification succeeds."""
    swagger_dict = {
        "swagger": "2.0",
        "info": {"title": "Swagger API", "version": "1.0.0"},
        "paths": {},
    }
    loader = OpenAPILoader.from_dict(swagger_dict)
    spec = loader.load()
    assert spec.title == "Swagger API"


def test_unsupported_openapi_version() -> None:
    """Test loading an unsupported OpenAPI/Swagger version (e.g., 4.0.0)."""
    invalid_dict = {
        "openapi": "4.0.0",
        "info": {"title": "Future API"},
        "paths": {},
    }
    loader = OpenAPILoader.from_dict(invalid_dict)

    pattern = re.escape("Specification version '4.0.0' is not supported.")
    with pytest.raises(UnsupportedVersionError, match=pattern):
        loader.load()


def test_empty_content(tmp_path: Path) -> None:
    """Test loading an empty file raises SpecLoadError."""
    file_path = tmp_path / "empty.json"
    file_path.write_text("   \n", encoding="utf-8")

    loader = OpenAPILoader.from_file(file_path)
    with pytest.raises(SpecLoadError, match="Specification content is empty"):
        loader.load()
