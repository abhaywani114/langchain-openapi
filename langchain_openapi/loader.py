"""OpenAPI Specification Loader."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from langchain_openapi.exceptions import SpecLoadError
from langchain_openapi.parser import OpenAPISpec
from langchain_openapi.utils import parse_json_or_yaml, validate_raw_spec

logger = logging.getLogger(__name__)


class OpenAPILoader:
    """Loader for obtaining normalized OpenAPI specifications from various sources.

    Supported sources include local JSON/YAML files, remote URLs, and in-memory dicts.
    """

    def __init__(
        self,
        load_fn: Callable[[], dict[str, Any]],
        source_info: str,
    ) -> None:
        """Initialize loader with a fetch callable and a source description string.

        Args:
            load_fn: A zero-argument callable that returns a raw spec dictionary.
            source_info: Human-readable description of the source for logging.
        """
        self._load_fn = load_fn
        self._source_info = source_info

    @classmethod
    def from_url(
        cls,
        url: str,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> "OpenAPILoader":
        """Create an OpenAPILoader for a remote URL source.

        Args:
            url: HTTP or HTTPS URL of the OpenAPI specification.
            timeout: Request timeout in seconds (default: 30.0).
            headers: Optional dictionary of HTTP headers for the request.

        Returns:
            An OpenAPILoader instance configured for URL fetching.
        """

        def _fetch_from_url() -> dict[str, Any]:
            logger.info("Loading OpenAPI specification from URL: %s", url)
            req_headers = {"User-Agent": "langchain-openapi"}
            if headers:
                req_headers.update(headers)

            try:
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    response = client.get(url, headers=req_headers)
                    response.raise_for_status()
                    content = response.text
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch OpenAPI spec from URL '%s': %s", url, exc)
                raise SpecLoadError(
                    f"Failed to fetch specification from URL '{url}': {exc}"
                ) from exc

            return parse_json_or_yaml(content)

        return cls(load_fn=_fetch_from_url, source_info=f"URL '{url}'")

    @classmethod
    def from_file(cls, file_path: str | Path) -> "OpenAPILoader":
        """Create an OpenAPILoader for a local JSON or YAML file source.

        Args:
            file_path: Path to the local OpenAPI specification file.

        Returns:
            An OpenAPILoader instance configured for file loading.
        """
        path = Path(file_path)

        def _read_from_file() -> dict[str, Any]:
            logger.info("Loading OpenAPI specification from file: %s", path)
            if not path.exists():
                logger.error("Specification file does not exist: %s", path)
                raise SpecLoadError(f"Specification file not found: '{path}'")

            if not path.is_file():
                logger.error("Path is not a regular file: %s", path)
                raise SpecLoadError(f"Path is not a regular file: '{path}'")

            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.error("Error reading specification file '%s': %s", path, exc)
                raise SpecLoadError(
                    f"Error reading specification file '{path}': {exc}"
                ) from exc

            return parse_json_or_yaml(content)

        return cls(load_fn=_read_from_file, source_info=f"file '{path}'")

    @classmethod
    def from_dict(cls, spec_dict: dict[str, Any]) -> "OpenAPILoader":
        """Create an OpenAPILoader from an in-memory dictionary.

        Args:
            spec_dict: Raw Python dictionary containing the OpenAPI specification.

        Returns:
            An OpenAPILoader instance configured for dictionary loading.
        """

        def _get_from_dict() -> dict[str, Any]:
            logger.info("Loading OpenAPI specification from in-memory dictionary")
            return spec_dict

        return cls(load_fn=_get_from_dict, source_info="in-memory dictionary")

    def load(self) -> OpenAPISpec:
        """Load, validate, and normalize the OpenAPI specification.

        Returns:
            An OpenAPISpec instance containing the normalized specification data.

        Raises:
            SpecLoadError: If loading from source or parsing JSON/YAML fails.
            InvalidSpecError: If required fields ('openapi', 'paths') are missing.
            UnsupportedVersionError: If the OpenAPI version is unsupported.
        """
        raw_data = self._load_fn()
        validate_raw_spec(raw_data)
        spec = OpenAPISpec.from_dict(raw_data)

        logger.info(
            "Successfully loaded OpenAPI spec '%s' (OpenAPI version %s) from %s",
            spec.title,
            spec.version,
            self._source_info,
        )
        return spec
