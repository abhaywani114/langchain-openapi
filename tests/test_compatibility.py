"""Tests for compatibility layer and primary package."""

import pytest

import langchain_openapi_tools


def test_primary_package_import() -> None:
    """Test importing from primary package langchain_openapi_tools."""
    from langchain_openapi_tools import OpenAPIToolkit, OpenAPIToolkitConfig

    assert OpenAPIToolkit is not None
    assert OpenAPIToolkitConfig is not None
    assert hasattr(langchain_openapi_tools, "__version__")


def test_compatibility_package_import_warning() -> None:
    """Test importing from legacy package issues a DeprecationWarning."""
    with pytest.deprecated_call(
        match="Importing from 'langchain_openapi' is deprecated."
    ):
        import langchain_openapi  # noqa: F401


def test_compatibility_package_exports() -> None:
    """Test compatibility package re-exports all symbols from primary package."""
    import langchain_openapi
    import langchain_openapi_tools

    assert langchain_openapi.__all__ == langchain_openapi_tools.__all__

    for name in langchain_openapi.__all__:
        primary_symbol = getattr(langchain_openapi_tools, name)
        compat_symbol = getattr(langchain_openapi, name)
        assert compat_symbol is primary_symbol
