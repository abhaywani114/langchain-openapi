"""Specification adapter layer.

This module implements the unified ingestion pipeline that transforms any
supported API specification (Swagger 2.0, OpenAPI 3.0, OpenAPI 3.1) into a
single normalized OpenAPI 3.x dictionary. Every downstream component
(``OpenAPIParser``, ``SchemaConverter``, ``RequestBuilder``, ...) operates
against the normalized shape and never inspects the original spec version.

Layering::

                    API Specification
                           │
          ┌────────────────┴────────────────┐
          │                                 │
     Swagger 2.0                     OpenAPI 3.x
          │                                 │
          ▼                                 ▼
   Swagger2Adapter                 OpenAPI3Adapter
          └──────────────┬──────────────────┘
                         ▼
              Normalized Internal Spec

Adapters are stateless and receive an optional ``source_url`` for base-URL
resolution when the spec omits ``servers`` / ``host``.
"""

from __future__ import annotations

from typing import Any, Protocol


class SpecAdapter(Protocol):
    """Protocol for specification-version adapters.

    An adapter accepts a raw specification dictionary and returns a
    normalized OpenAPI 3.x dictionary. The returned document is the sole
    input consumed by the rest of the pipeline.
    """

    def normalize(
        self, spec_dict: dict[str, Any], source_url: str | None = None
    ) -> dict[str, Any]:
        """Return a normalized OpenAPI 3.x dictionary."""


class Swagger2Adapter:
    """Adapter for Swagger 2.0 (a.k.a. OpenAPI 2.0) specifications.

    Delegates to ``SwaggerNormalizer`` for the actual field-by-field
    translation, then relies on the pipeline's OpenAPI 3.x processing for
    everything downstream.
    """

    def normalize(
        self, spec_dict: dict[str, Any], source_url: str | None = None
    ) -> dict[str, Any]:
        from langchain_openapi_tools.swagger import SwaggerNormalizer

        return SwaggerNormalizer(spec_dict, source_url=source_url).normalize()


class OpenAPI3Adapter:
    """Adapter for OpenAPI 3.0 and 3.1 specifications.

    OpenAPI 3.x documents already match the internal normalized shape, so
    the adapter primarily performs the following:

    * Ensures the document has an ``openapi`` field.
    * Backfills ``jsonSchemaDialect`` for 3.1 documents that omit it.
    * Leaves ``servers`` / ``components`` untouched; base-URL resolution is
      handled by :class:`langchain_openapi_tools.parser.OpenAPISpec`.
    """

    def normalize(
        self, spec_dict: dict[str, Any], source_url: str | None = None
    ) -> dict[str, Any]:
        return spec_dict


def detect_spec_version(spec_dict: dict[str, Any]) -> str:
    """Detect the spec version family: ``"swagger2"``, ``"openapi30"``, ``"openapi31"``.

    Raises ``UnsupportedVersionError`` for anything else.
    """
    from langchain_openapi_tools.exceptions import UnsupportedVersionError

    swagger = str(spec_dict.get("swagger", ""))
    if swagger == "2.0" or swagger.startswith("2."):
        return "swagger2"

    openapi = str(spec_dict.get("openapi", ""))
    if openapi.startswith("3.0"):
        return "openapi30"
    if openapi.startswith("3.1"):
        return "openapi31"

    raise UnsupportedVersionError(
        f"Unsupported specification version: swagger={swagger!r}, openapi={openapi!r}."
    )


def select_adapter(spec_dict: dict[str, Any]) -> SpecAdapter:
    """Return the correct :class:`SpecAdapter` for the given raw spec dict."""
    family = detect_spec_version(spec_dict)
    if family == "swagger2":
        return Swagger2Adapter()
    return OpenAPI3Adapter()


def normalize_spec(
    spec_dict: dict[str, Any], source_url: str | None = None
) -> tuple[dict[str, Any], str]:
    """Normalize any supported spec into an OpenAPI 3.x dictionary.

    Args:
        spec_dict: Raw specification dictionary (Swagger 2.0 or OpenAPI 3.x).
        source_url: Optional URL the specification was fetched from.

    Returns:
        Tuple of ``(normalized_dict, family)`` where ``family`` is one of
        ``"swagger2"``, ``"openapi30"``, ``"openapi31"``.
    """
    family = detect_spec_version(spec_dict)
    adapter = select_adapter(spec_dict)
    normalized = adapter.normalize(spec_dict, source_url=source_url)
    return normalized, family
