"""Utility functions for parsing, validation, logging, and sanitization."""

import json
import re
from typing import Any

import yaml

from langchain_openapi.exceptions import (
    InvalidSpecError,
    SpecLoadError,
    UnsupportedVersionError,
)


def parse_json_or_yaml(content: str) -> dict[str, Any]:
    """Parse raw JSON or YAML string into a Python dictionary.

    Args:
        content: Raw content string in JSON or YAML format.

    Returns:
        Parsed specification dictionary.

    Raises:
        SpecLoadError: If content cannot be parsed as JSON or YAML.
        InvalidSpecError: If JSON content is not a dictionary object.
    """
    if not content or not content.strip():
        raise SpecLoadError("Specification content is empty.")

    # Try JSON first
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
        raise InvalidSpecError(
            f"Specification content must be a JSON object, got {type(data).__name__}."
        )
    except json.JSONDecodeError:
        pass

    # Try YAML next
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            return data
        raise SpecLoadError(
            f"Failed to parse specification content, got {type(data).__name__}."
        )
    except yaml.YAMLError as exc:
        raise SpecLoadError(f"Failed to parse specification content: {exc}") from exc


def validate_raw_spec(spec_dict: dict[str, Any]) -> None:
    """Validate that raw dictionary contains required OpenAPI fields.

    Args:
        spec_dict: OpenAPI specification dictionary.

    Raises:
        InvalidSpecError: If required fields are missing or invalid type.
        UnsupportedVersionError: If OpenAPI version is not 3.0+ or 3.1+.
    """
    if not isinstance(spec_dict, dict):
        raise InvalidSpecError("Specification must be a dictionary.")

    version = spec_dict.get("openapi") or spec_dict.get("swagger")
    if not version:
        raise InvalidSpecError(
            "Specification is missing required field: 'openapi' or 'swagger'."
        )

    version_str = str(version)
    if version_str.startswith("2."):
        raise UnsupportedVersionError(
            f"Swagger version '{version_str}' is not supported."
        )

    if not (version_str.startswith("3.0") or version_str.startswith("3.1")):
        raise UnsupportedVersionError(
            f"OpenAPI version '{version_str}' is not supported."
        )

    if "paths" not in spec_dict:
        raise InvalidSpecError("Specification is missing required field: 'paths'.")

    if not isinstance(spec_dict.get("paths"), dict):
        raise InvalidSpecError("The 'paths' field must be a dictionary.")


def sanitize_request_log(method: str, url: str) -> str:
    """Sanitize request URL to prevent logging secret credentials or tokens.

    Args:
        method: HTTP method name.
        url: Target request URL string.

    Returns:
        Sanitized log representation.
    """
    sanitized_url = re.sub(
        r"((?:api_key|key|token|auth|secret|password|access_token)=)[^&]+",
        r"\1[REDACTED]",
        str(url),
        flags=re.IGNORECASE,
    )
    return f"{method.upper()} '{sanitized_url}'"
