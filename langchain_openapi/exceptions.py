"""Custom exceptions for langchain-openapi."""


class OpenAPIError(Exception):
    """Base exception for all langchain-openapi errors."""


class SpecLoadError(OpenAPIError):
    """Raised when an OpenAPI specification cannot be loaded from a source."""


class InvalidSpecError(OpenAPIError):
    """Raised when a loaded specification fails validation requirements."""


class UnsupportedVersionError(OpenAPIError):
    """Raised when the specification uses an unsupported OpenAPI or Swagger version."""


class HTTPExecutionError(OpenAPIError):
    """Base exception for HTTP request execution errors."""


class AuthenticationError(HTTPExecutionError):
    """Raised when authentication credentials fail or cannot be applied."""


class ProviderError(HTTPExecutionError):
    """Raised when a request provider fails during request mutation."""


class RequestValidationError(HTTPExecutionError):
    """Raised when request arguments are invalid or missing required parameters."""


class ResponseParsingError(HTTPExecutionError):
    """Raised when an HTTP response payload cannot be parsed."""


class ExecutionTimeoutError(HTTPExecutionError):
    """Raised when an HTTP request times out."""
