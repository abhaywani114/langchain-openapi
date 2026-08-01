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
from langchain_openapi_tools.models import Operation
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
        if operation.request_body:
            if "body" in arguments:
                json_body = arguments["body"]
            else:
                unconsumed = {
                    k: v for k, v in arguments.items() if k not in consumed_args
                }
                if unconsumed:
                    json_body = unconsumed

            if json_body is not None and "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"

        return BuiltRequest(
            method=method,
            url=full_url,
            headers=headers,
            params=query_params,
            json_body=json_body,
            cookies=cookies,
        )


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
            "json": req_data.json_body,
            "timeout": self.timeout,
        }

        request = client.build_request(**kwargs)

        if req_data.cookies:
            cookie_hdr = "; ".join(f"{k}={v}" for k, v in req_data.cookies.items())
            request.headers["Cookie"] = cookie_hdr

        request = await self.provider.apply(request)

        async def transport_call(req: httpx.Request) -> httpx.Response:
            return await client.send(req)

        return await self.pipeline.execute(request, transport_call)
