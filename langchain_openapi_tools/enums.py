"""Enumerations for OpenAPI specification entities."""

from enum import StrEnum


class HTTPMethod(StrEnum):
    """Supported HTTP request methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


class ParameterLocation(StrEnum):
    """Locations where parameters can be supplied in an HTTP request."""

    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


class DataType(StrEnum):
    """Core data types supported in OpenAPI schemas."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
