"""Internal normalized models for OpenAPI specification entities.

Note on Limitations:
    Current parser models skip polymorphic constructs (oneOf, anyOf, allOf,
    discriminator), callbacks, links, webhooks, and complex example inheritance
    patterns. These features will be evaluated in future milestones.
"""

from dataclasses import dataclass, field
from typing import Any

from langchain_openapi_tools.enums import DataType, HTTPMethod, ParameterLocation


@dataclass
class Schema:
    """Represents a data type schema definition.

    Attributes:
        type: The data type (e.g. 'string', 'integer', 'object', 'array').
        format: Optional format modifier (e.g. 'date-time', 'email', 'uuid').
        properties: Dictionary of property schemas if type is 'object'.
        items: Schema of array elements if type is 'array'.
        required: List of required property names if type is 'object'.
        enum: List of allowed values for enum types.
        default: Default value for the schema.
        nullable: Whether null values are permitted.
        description: Description of the schema element.
    """

    type: DataType | str | list[DataType | str] | None = None
    format: str | None = None
    properties: dict[str, "Schema"] | None = None
    items: "Schema | None" = None
    required: list[str] | None = None
    enum: list[Any] | None = None
    default: Any = None
    nullable: bool = False
    description: str | None = None


@dataclass
class MediaType:
    """Represents a media type definition (e.g., 'application/json').

    Attributes:
        content_type: MIME type string (e.g., 'application/json').
        schema: Optional Schema instance defining the payload structure.
        example: Single example value for this media type.
        examples: Dictionary of named example objects.
    """

    content_type: str
    schema: Schema | None = None
    example: Any = None
    examples: dict[str, Any] | None = None


@dataclass
class Parameter:
    """Represents an operation parameter (path, query, header, or cookie).

    Attributes:
        name: Parameter name.
        location: Parameter location (path, query, header, cookie).
        required: Whether the parameter is required.
        description: Parameter description.
        schema: Optional Schema defining the parameter value type.
        default: Default value for the parameter.
        example: Example value for the parameter.
        style: Parameter serialization style modifier.
        explode: Whether parameter array/object items explode into separate values.
    """

    name: str
    location: ParameterLocation
    required: bool = False
    description: str | None = None
    schema: Schema | None = None
    default: Any = None
    example: Any = None
    style: str | None = None
    explode: bool | None = None


@dataclass
class RequestBody:
    """Represents an operation request payload definition.

    Attributes:
        required: Whether a request body is mandatory.
        description: Request body description.
        content: Map of MIME content types to MediaType instances.
    """

    required: bool = False
    description: str | None = None
    content: dict[str, MediaType] = field(default_factory=dict)


@dataclass
class Response:
    """Represents an HTTP response status definition.

    Attributes:
        status_code: HTTP status code string (e.g., '200', '404', 'default').
        description: Response description.
        content: Map of MIME content types to MediaType instances.
    """

    status_code: str
    description: str
    content: dict[str, MediaType] = field(default_factory=dict)


@dataclass
class Operation:
    """Represents a single API operation corresponding to an HTTP method on a path.

    Attributes:
        name: Resolved operation identifier (or generated fallback name).
        summary: Short summary of the operation.
        description: Detailed description of the operation.
        method: HTTP method (GET, POST, etc.).
        path: Path template (e.g., '/users/{id}').
        operation_id: Explicit operationId if declared in spec.
        tags: Tags associated with the operation.
        parameters: List of Parameter objects for path, query, headers, cookies.
        request_body: Optional RequestBody instance for request payloads.
        responses: Map of HTTP status code strings to Response objects.
        deprecated: Whether the operation is deprecated.
        security: List of security requirement maps for this operation.
    """

    name: str
    method: HTTPMethod
    path: str
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    tags: list[str] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    request_body: RequestBody | None = None
    responses: dict[str, Response] = field(default_factory=dict)
    deprecated: bool = False
    security: list[dict[str, list[str]]] = field(default_factory=list)
