"""Asynchronous HTTP execution engine for OpenAPI Operations."""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx

from langchain_openapi_tools.enums import ParameterLocation
from langchain_openapi_tools.exceptions import (
    ExecutionTimeoutError,
    HTTPExecutionError,
    RequestValidationError,
    ResponseParsingError,
)
from langchain_openapi_tools.middleware import Middleware, MiddlewarePipeline
from langchain_openapi_tools.models import Operation, RequestBody
from langchain_openapi_tools.providers import NoAuthProvider, RequestProvider
from langchain_openapi_tools.utils import sanitize_request_log

logger = logging.getLogger(__name__)


@dataclass
class BuiltRequest:
    """Container for constructed request metadata ready for execution."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    json_body: Any = None
    cookies: dict[str, str] = field(default_factory=dict)
    data: Any = None
    files: dict[str, Any] | None = None
    content: bytes | str | None = None


@dataclass
class ResponseData:
    """Normalized response payload."""

    status_code: int
    headers: dict[str, str]
    body: Any
    raw: httpx.Response


def create_async_client(
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Create a configured httpx.AsyncClient instance."""
    return httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        cookies=cookies,
        **kwargs,
    )


class RequestBuilder:
    """Translates Operation models into BuiltRequest instances."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url.rstrip("/") if base_url else ""

    def build(
        self,
        operation: Operation,
        arguments: dict[str, Any],
        base_url_override: str | None = None,
    ) -> BuiltRequest:
        method = operation.method.value.upper()
        base_url = base_url_override.rstrip("/") if base_url_override else self.base_url

        path_template = operation.path
        query_params: dict[str, Any] = {}
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}
        consumed_args: set[str] = set()

        if arguments.get("paginate") or arguments.get("__paginate__"):
            headers["X-LangChain-Paginate"] = "true"
            consumed_args.add("paginate")
            consumed_args.add("__paginate__")

        for param in operation.parameters:
            name = param.name
            val = arguments.get(name)

            if param.location == ParameterLocation.PATH:
                if val is None:
                    raise RequestValidationError(
                        f"Missing required path parameter '{name}' "
                        f"for operation '{operation.name}'."
                    )
                path_template = path_template.replace(f"{{{name}}}", str(val))
                consumed_args.add(name)

            elif param.location == ParameterLocation.QUERY:
                if val is not None:
                    query_params[name] = val
                    consumed_args.add(name)

            elif param.location == ParameterLocation.HEADER:
                if val is not None:
                    headers[name] = str(val)
                    consumed_args.add(name)

            elif param.location == ParameterLocation.COOKIE:
                if val is not None:
                    cookies[name] = str(val)
                    consumed_args.add(name)

        if path_template.startswith("http://") or path_template.startswith("https://"):
            full_url = path_template
        elif base_url:
            base_url_with_slash = base_url if base_url.endswith("/") else f"{base_url}/"
            full_url = urljoin(base_url_with_slash, path_template.lstrip("/"))
        else:
            full_url = path_template

        json_body: Any = None
        form_data: Any = None
        multipart_files: dict[str, Any] | None = None
        raw_content: bytes | str | None = None

        if operation.request_body:
            body_value: Any
            if "body" in arguments:
                body_value = arguments["body"]
            else:
                unconsumed = {
                    k: v for k, v in arguments.items() if k not in consumed_args
                }
                body_value = unconsumed if unconsumed else None

            # StructuredTool validates args through a dynamic Pydantic model,
            # so complex bodies arrive here as BaseModel instances. Serialize
            # them to plain Python structures before dispatch so ``httpx`` /
            # ``urlencode`` can encode them.
            body_value = _coerce_body_value(body_value)

            if body_value is not None:
                content_type = _select_body_content_type(
                    operation.request_body, headers.get("Content-Type")
                )

                if content_type.startswith("multipart/form-data"):
                    multipart_files = _to_multipart_files(body_value)
                    # httpx will set the Content-Type + boundary automatically.
                    headers.pop("Content-Type", None)
                elif content_type == "application/x-www-form-urlencoded":
                    form_data = body_value
                    headers.setdefault("Content-Type", content_type)
                elif content_type.endswith("/json") or content_type.endswith("+json"):
                    json_body = body_value
                    headers.setdefault("Content-Type", "application/json")
                elif (
                    content_type.startswith("text/")
                    or content_type == "application/xml"
                ):
                    raw_content = (
                        body_value
                        if isinstance(body_value, (str, bytes))
                        else str(body_value)
                    )
                    headers.setdefault("Content-Type", content_type)
                else:
                    # Default: JSON encoding for unknown content types.
                    json_body = body_value
                    headers.setdefault("Content-Type", "application/json")

        return BuiltRequest(
            method=method,
            url=full_url,
            headers=headers,
            params=query_params,
            json_body=json_body,
            cookies=cookies,
            data=form_data,
            files=multipart_files,
            content=raw_content,
        )


_JSON_LIKE = ("application/json",)


def _coerce_body_value(body_value: Any) -> Any:
    """Convert Pydantic models / enum values inside a body into plain data.

    ``StructuredTool`` runs incoming arguments through a dynamically
    generated Pydantic model. Any request body typed as an object therefore
    arrives here as a ``BaseModel`` instance (or a dict containing such
    instances or ``Enum`` members). Convert everything back to JSON-safe
    Python primitives before dispatching to httpx / urlencode.
    """
    if body_value is None:
        return None
    # Pydantic v2 BaseModel.
    if hasattr(body_value, "model_dump"):
        try:
            return body_value.model_dump(mode="json", exclude_none=True)
        except Exception:
            return body_value.model_dump()
    if isinstance(body_value, dict):
        return {k: _coerce_body_value(v) for k, v in body_value.items()}
    if isinstance(body_value, list):
        return [_coerce_body_value(v) for v in body_value]
    # Enum values from generated dynamic Enums.
    value_attr = getattr(body_value, "value", None)
    if value_attr is not None and not callable(value_attr) and not isinstance(
        body_value, (str, int, float, bool, bytes)
    ):
        return value_attr
    return body_value


def _select_body_content_type(
    request_body: "RequestBody", explicit_header: str | None
) -> str:
    """Pick the request body's Content-Type in a version-agnostic way.

    Priority:
    1. Explicit ``Content-Type`` header supplied via arguments.
    2. ``application/json`` (or ``+json`` variant) if the operation declares one.
    3. The first declared media type on the operation.
    4. Fallback to ``application/json``.
    """
    if explicit_header:
        return explicit_header

    content = request_body.content or {}
    if not content:
        return "application/json"

    for key in content.keys():
        if key == "application/json" or key.endswith("+json") or key.startswith(
            "application/json"
        ):
            return key
    # First declared media type wins if no JSON variant present.
    return next(iter(content.keys()))


def _to_multipart_files(body: Any) -> dict[str, Any]:
    """Convert a body dict into an httpx-compatible ``files`` mapping.

    Values that are bytes / file-like tuples are treated as file uploads;
    other scalars are sent as regular multipart form fields (via httpx's
    ``(None, value)`` tuple convention).
    """
    if not isinstance(body, dict):
        return {"file": body}

    files: dict[str, Any] = {}
    for key, value in body.items():
        if isinstance(value, (bytes, bytearray)):
            files[key] = (key, bytes(value))
        elif isinstance(value, tuple):
            files[key] = value
        elif hasattr(value, "read"):
            files[key] = (getattr(value, "name", key), value)
        else:
            # Regular form field alongside the file upload(s).
            files[key] = (None, str(value))
    return files


class ResponseParser:
    """Attempts JSON decoding and standardizes HTTP responses."""

    def parse(self, response: httpx.Response) -> ResponseData:
        try:
            status_code = response.status_code
            headers = dict(response.headers)

            if response.content:
                try:
                    body: Any = response.json()
                except Exception:
                    body = response.text
            else:
                body = None

            return ResponseData(
                status_code=status_code,
                headers=headers,
                body=body,
                raw=response,
            )
        except Exception as exc:
            raise ResponseParsingError(
                f"Failed to parse HTTP response from '{response.url}': {exc}"
            ) from exc


class AsyncHTTPExecutor:
    """Generic asynchronous HTTP executor for executing OpenAPI operations."""

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url
        self._client = client
        self.provider = provider if provider is not None else NoAuthProvider()
        self.pipeline = MiddlewarePipeline(middleware)
        self.timeout = timeout
        self._builder = RequestBuilder(base_url=base_url)
        self._parser = ResponseParser()

    async def execute(
        self,
        operation: Operation,
        arguments: dict[str, Any],
        base_url_override: str | None = None,
    ) -> ResponseData:
        built_req = self._builder.build(
            operation=operation,
            arguments=arguments,
            base_url_override=base_url_override,
        )
        return await self._dispatch(built_req)

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        json_body: Any = None,
        cookies: dict[str, str] | None = None,
        data: Any = None,
        content: bytes | str | None = None,
        files: dict[str, Any] | None = None,
        base_url_override: str | None = None,
    ) -> ResponseData:
        """Execute a raw HTTP request through the shared provider + middleware.

        Used by the Generic HTTP Toolkit so a small, fixed number of tools
        (``GET``/``POST``/``PUT``/``PATCH``/``DELETE``) can share the same
        execution stack as the typed toolkit — including authentication,
        retries, rate limiting, caching, and logging.

        Args:
            method: HTTP method (case-insensitive).
            endpoint: Absolute URL or a path/URL fragment to resolve against
                ``base_url_override`` or the executor's own ``base_url``.
            params: Query string parameters.
            headers: Request headers.
            json_body: JSON body payload (mutually exclusive with ``data`` /
                ``content`` / ``files``).
            cookies: Cookies to attach to the request.
            data: URL-encoded form or raw form data.
            content: Raw request body (str or bytes).
            files: Multipart file uploads.
            base_url_override: Optional base URL override for this call.

        Returns:
            A :class:`ResponseData` with parsed body, status, and headers.
        """
        base_url = base_url_override or self.base_url or ""
        endpoint = endpoint or ""

        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            full_url = endpoint
        elif base_url:
            base_with_slash = base_url if base_url.endswith("/") else f"{base_url}/"
            full_url = urljoin(base_with_slash, endpoint.lstrip("/"))
        else:
            full_url = endpoint

        normalized_headers: dict[str, str] = {}
        if headers:
            for hk, hv in headers.items():
                if hv is None:
                    continue
                normalized_headers[str(hk)] = str(hv)

        normalized_cookies: dict[str, str] = {}
        if cookies:
            for ck, cv in cookies.items():
                if cv is None:
                    continue
                normalized_cookies[str(ck)] = str(cv)

        if (
            json_body is not None
            and data is None
            and content is None
            and files is None
        ):
            normalized_headers.setdefault("Content-Type", "application/json")

        built_req = BuiltRequest(
            method=method.upper(),
            url=full_url,
            headers=normalized_headers,
            params={k: v for k, v in (params or {}).items() if v is not None},
            json_body=json_body,
            cookies=normalized_cookies,
            data=data,
            files=files,
            content=content,
        )
        return await self._dispatch(built_req)

    async def _dispatch(self, built_req: BuiltRequest) -> ResponseData:
        start_time = time.monotonic()

        try:
            if self._client is not None:
                response = await self._send_request(self._client, built_req)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await self._send_request(client, built_req)
        except httpx.TimeoutException as exc:
            logger.error(
                "Request timed out for %s after %.1fs",
                sanitize_request_log(built_req.method, built_req.url),
                self.timeout,
            )
            raise ExecutionTimeoutError(
                f"HTTP request to '{built_req.url}' timed out after {self.timeout}s."
            ) from exc
        except (RequestValidationError, ResponseParsingError):
            raise
        except httpx.HTTPError as exc:
            logger.error(
                "HTTP execution failed for %s: %s",
                sanitize_request_log(built_req.method, built_req.url),
                exc,
            )
            raise HTTPExecutionError(
                f"HTTP request execution failed for '{built_req.url}': {exc}"
            ) from exc

        elapsed = time.monotonic() - start_time
        logger.info(
            "Executed HTTP %s -> Status %d (%.3fs)",
            sanitize_request_log(built_req.method, built_req.url),
            response.status_code,
            elapsed,
        )

        return self._parser.parse(response)

    async def _send_request(
        self, client: httpx.AsyncClient, req_data: BuiltRequest
    ) -> httpx.Response:
        kwargs: dict[str, Any] = {
            "method": req_data.method,
            "url": req_data.url,
            "headers": req_data.headers,
            "params": req_data.params,
            "timeout": self.timeout,
        }

        # Media-type-aware body assignment: exactly one of these should be set.
        if req_data.files is not None:
            kwargs["files"] = req_data.files
            if req_data.data is not None:
                kwargs["data"] = req_data.data
        elif req_data.data is not None:
            kwargs["data"] = req_data.data
        elif req_data.content is not None:
            kwargs["content"] = req_data.content
        elif req_data.json_body is not None:
            kwargs["json"] = req_data.json_body

        request = client.build_request(**kwargs)

        if req_data.cookies:
            cookie_hdr = "; ".join(f"{k}={v}" for k, v in req_data.cookies.items())
            request.headers["Cookie"] = cookie_hdr

        request = await self.provider.apply(request)

        async def transport_call(req: httpx.Request) -> httpx.Response:
            return await client.send(req)

        return await self.pipeline.execute(request, transport_call)
