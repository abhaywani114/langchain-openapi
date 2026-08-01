"""Tests for the SpecAdapter architecture.

Verifies that the version detection dispatches to the correct adapter and
that the normalized output shape is version-agnostic for downstream
components.
"""

from __future__ import annotations

import pytest

from langchain_openapi_tools import (
    OpenAPI3Adapter,
    OpenAPISpec,
    Swagger2Adapter,
    UnsupportedVersionError,
    detect_spec_version,
    normalize_spec,
    select_adapter,
)


def test_detect_swagger_2() -> None:
    assert detect_spec_version({"swagger": "2.0"}) == "swagger2"


def test_detect_openapi_30() -> None:
    assert detect_spec_version({"openapi": "3.0.3"}) == "openapi30"


def test_detect_openapi_31() -> None:
    assert detect_spec_version({"openapi": "3.1.0"}) == "openapi31"


def test_detect_unsupported_version_raises() -> None:
    with pytest.raises(UnsupportedVersionError):
        detect_spec_version({"openapi": "4.0.0"})


def test_select_adapter_swagger() -> None:
    assert isinstance(select_adapter({"swagger": "2.0"}), Swagger2Adapter)


def test_select_adapter_openapi() -> None:
    assert isinstance(select_adapter({"openapi": "3.1.0"}), OpenAPI3Adapter)


def test_normalize_spec_swagger_produces_openapi_3() -> None:
    raw = {
        "swagger": "2.0",
        "info": {"title": "S", "version": "1"},
        "host": "api.example.com",
        "basePath": "/v1",
        "schemes": ["https"],
        "paths": {"/x": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }
    normalized, family = normalize_spec(raw)
    assert family == "swagger2"
    assert normalized["openapi"].startswith("3.")
    assert normalized["servers"] == [{"url": "https://api.example.com/v1"}]


def test_normalize_spec_openapi_3x_pass_through() -> None:
    raw = {
        "openapi": "3.1.0",
        "info": {"title": "O", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {},
    }
    normalized, family = normalize_spec(raw)
    assert family == "openapi31"
    # OpenAPI3Adapter returns the document unchanged.
    assert normalized is raw


def test_spec_family_recorded_on_openapispec_swagger() -> None:
    raw = {
        "swagger": "2.0",
        "info": {"title": "S", "version": "1"},
        "host": "api.example.com",
        "schemes": ["https"],
        "paths": {},
    }
    spec = OpenAPISpec.from_dict(raw)
    assert spec.spec_family == "swagger2"


def test_spec_family_recorded_on_openapispec_31() -> None:
    raw = {
        "openapi": "3.1.0",
        "info": {"title": "T", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {},
    }
    spec = OpenAPISpec.from_dict(raw)
    assert spec.spec_family == "openapi31"
