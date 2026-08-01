"""Compatibility wrapper for langchain_openapi.

Importing from 'langchain_openapi' is deprecated. Please use 'langchain_openapi_tools'.
"""

import warnings

import langchain_openapi_tools
from langchain_openapi_tools import *  # noqa: F403

warnings.warn(
    "Importing from 'langchain_openapi' is deprecated. "
    "Please use 'langchain_openapi_tools' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = langchain_openapi_tools.__all__
__version__ = langchain_openapi_tools.__version__
