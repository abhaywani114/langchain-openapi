"""Production middleware pipeline for request/response handling."""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol, runtime_checkable

import httpx

from langchain_openapi_tools.utils import sanitize_request_log

logger = logging.getLogger(__name__)

NextCallable = Callable[[httpx.Request], Awaitable[httpx.Response]]


@runtime_checkable
class Middleware(Protocol):
    """Protocol for HTTP request/response middleware components."""

    async def dispatch(
        self,
        request: httpx.Request,
        call_next: NextCallable,
    ) -> httpx.Response: ...


class MiddlewarePipeline:
    """Orchestrates sequential execution of a list of Middleware instances."""

    def __init__(self, middlewares: Sequence[Middleware] | None = None) -> None:
        self.middlewares = list(middlewares) if middlewares else []

    async def execute(
        self,
        request: httpx.Request,
        transport_call: NextCallable,
    ) -> httpx.Response:
        index = 0

        async def call_next(req: httpx.Request) -> httpx.Response:
            nonlocal index
            if index < len(self.middlewares):
                mw = self.middlewares[index]
                index += 1
                return await mw.dispatch(req, call_next)
            return await transport_call(req)

        return await call_next(request)


class RetryMiddleware(Middleware):
    """Middleware for retrying failed HTTP requests with configurable backoff."""

    def __init__(
        self,
        retries: int = 3,
        backoff: str = "exponential",
        backoff_factor: float = 0.5,
        retry_status_codes: Sequence[int] = (429, 500, 502, 503, 504),
    ) -> None:
        self.retries = retries
        self.backoff = backoff
        self.backoff_factor = backoff_factor
        self.retry_status_codes = set(retry_status_codes)

    async def dispatch(
        self,
        request: httpx.Request,
        call_next: NextCallable,
    ) -> httpx.Response:
        attempt = 0
        last_exception: Exception | None = None

        while attempt <= self.retries:
            try:
                response = await call_next(request)
                if (
                    response.status_code in self.retry_status_codes
                    and attempt < self.retries
                ):
                    attempt += 1
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        "Retrying %s (attempt %d/%d) after HTTP %d (delay %.2fs)",
                        request.url,
                        attempt,
                        self.retries,
                        response.status_code,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return response
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exception = exc
                if attempt < self.retries:
                    attempt += 1
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        "Retrying %s (attempt %d/%d) after error: %s (delay %.2fs)",
                        request.url,
                        attempt,
                        self.retries,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        if last_exception:
            raise last_exception
        return response

    def _calculate_delay(self, attempt: int) -> float:
        if self.backoff == "fixed":
            return float(self.backoff_factor)
        return float(self.backoff_factor * (2 ** (attempt - 1)))


class RateLimitMiddleware(Middleware):
    """Middleware for throttling HTTP requests using a token bucket algorithm."""

    def __init__(self, requests_per_second: float = 5.0) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero.")

        self.rate = float(requests_per_second)
        self.capacity = float(requests_per_second)
        self.tokens = float(requests_per_second)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def dispatch(
        self,
        request: httpx.Request,
        call_next: NextCallable,
    ) -> httpx.Response:
        await self._acquire_token()
        return await call_next(request)

    async def _acquire_token(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    break

                needed_tokens = 1.0 - self.tokens
                wait_time = needed_tokens / self.rate
                await asyncio.sleep(wait_time)


@runtime_checkable
class CacheBackend(Protocol):
    """Protocol interface for cache storage backends."""

    async def get(self, key: str) -> httpx.Response | None: ...

    async def set(self, key: str, response: httpx.Response, ttl: float) -> None: ...


class InMemoryCacheBackend(CacheBackend):
    """Default in-memory cache backend with TTL expiration."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[httpx.Response, float]] = {}

    async def get(self, key: str) -> httpx.Response | None:
        if key not in self._cache:
            return None

        response, expire_at = self._cache[key]
        if time.monotonic() > expire_at:
            del self._cache[key]
            return None

        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=response.content,
            request=response.request,
        )

    async def set(self, key: str, response: httpx.Response, ttl: float) -> None:
        expire_at = time.monotonic() + ttl
        content = (
            await response.aread() if hasattr(response, "aread") else response.content
        )
        cached_resp = httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=content,
            request=response.request,
        )
        self._cache[key] = (cached_resp, expire_at)


class CacheMiddleware(Middleware):
    """Middleware for caching HTTP GET responses."""

    def __init__(
        self,
        ttl: float = 300.0,
        backend: CacheBackend | None = None,
        cache_authenticated: bool = False,
    ) -> None:
        self.ttl = ttl
        self.backend = backend or InMemoryCacheBackend()
        self.cache_authenticated = cache_authenticated

    async def dispatch(
        self,
        request: httpx.Request,
        call_next: NextCallable,
    ) -> httpx.Response:
        if request.method.upper() != "GET":
            return await call_next(request)

        if not self.cache_authenticated and self._is_authenticated(request):
            return await call_next(request)

        key = self._generate_cache_key(request)

        cached = await self.backend.get(key)
        if cached is not None:
            logger.info("Cache hit for %s", request.url)
            return cached

        logger.info("Cache miss for %s", request.url)
        response = await call_next(request)

        if response.status_code == 200:
            await self.backend.set(key, response, self.ttl)

        return response

    def _is_authenticated(self, request: httpx.Request) -> bool:
        auth_headers = {"authorization", "cookie", "x-api-key"}
        return any(h.lower() in auth_headers for h in request.headers)

    def _generate_cache_key(self, request: httpx.Request) -> str:
        key_raw = f"{request.method.upper()}:{request.url}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()


class PaginationMiddleware(Middleware):
    """Middleware for automated multi-page result aggregation."""

    def __init__(
        self,
        max_pages: int = 10,
        max_items: int = 1000,
    ) -> None:
        self.max_pages = max_pages
        self.max_items = max_items

    async def dispatch(
        self,
        request: httpx.Request,
        call_next: NextCallable,
    ) -> httpx.Response:
        params = dict(request.url.params)
        is_paginate_flag = (
            request.headers.get("X-LangChain-Paginate", "").lower() == "true"
            or params.pop("__paginate__", "").lower() == "true"
        )

        if not is_paginate_flag:
            return await call_next(request)

        if "X-LangChain-Paginate" in request.headers:
            del request.headers["X-LangChain-Paginate"]
        request.url = request.url.copy_with(params=params)

        response = await call_next(request)
        if response.status_code != 200:
            return response

        try:
            initial_data = json.loads(response.text)
        except Exception:
            return response

        aggregated_items, data_key = self._extract_items(initial_data)
        if aggregated_items is None:
            return response

        base_payload = initial_data
        current_page = 1
        page_param_name, _current_val = self._detect_pagination_param(params)

        while current_page < self.max_pages and len(aggregated_items) < self.max_items:
            current_page += 1
            next_params = dict(params)

            if page_param_name == "page":
                next_params["page"] = str(current_page)
            elif page_param_name == "offset":
                limit = int(params.get("limit", len(aggregated_items)))
                next_params["offset"] = str((current_page - 1) * limit)
            elif page_param_name == "cursor" and isinstance(initial_data, dict):
                cursor_val = initial_data.get("next_cursor") or initial_data.get(
                    "cursor"
                )
                if not cursor_val:
                    break
                next_params["cursor"] = str(cursor_val)
            else:
                next_params["page"] = str(current_page)

            next_req = httpx.Request(
                method=request.method,
                url=request.url.copy_with(params=next_params),
                headers=request.headers,
                content=request.content,
            )

            page_resp = await call_next(next_req)
            if page_resp.status_code != 200:
                break

            try:
                page_data = json.loads(page_resp.text)
            except Exception:
                break

            page_items, _ = self._extract_items(page_data)
            if not page_items:
                break

            aggregated_items.extend(page_items)
            initial_data = page_data

            if len(aggregated_items) >= self.max_items:
                aggregated_items = aggregated_items[: self.max_items]
                break

        final_payload: Any
        if data_key is not None and isinstance(base_payload, dict):
            base_payload[data_key] = aggregated_items
            final_payload = base_payload
        else:
            final_payload = aggregated_items

        return httpx.Response(
            status_code=200,
            headers=response.headers,
            content=json.dumps(final_payload).encode("utf-8"),
            request=request,
        )

    def _extract_items(self, data: Any) -> tuple[list[Any] | None, str | None]:
        if isinstance(data, list):
            return list(data), None
        if isinstance(data, dict):
            for key in ("items", "data", "results", "records"):
                if key in data and isinstance(data[key], list):
                    return list(data[key]), key
        return None, None

    def _detect_pagination_param(self, params: dict[str, str]) -> tuple[str, str]:
        for p in ("page", "offset", "cursor"):
            if p in params:
                return p, params[p]
        return "page", "1"


class LoggingMiddleware(Middleware):
    """Middleware for logging HTTP request/response metrics."""

    def __init__(self, logger_instance: logging.Logger | None = None) -> None:
        self.logger = logger_instance or logger

    async def dispatch(
        self,
        request: httpx.Request,
        call_next: NextCallable,
    ) -> httpx.Response:
        sanitized = sanitize_request_log(request.method, str(request.url))
        start_time = time.monotonic()
        self.logger.info("HTTP Request: %s", sanitized)

        try:
            response = await call_next(request)
            elapsed = time.monotonic() - start_time
            self.logger.info(
                "HTTP Response: %s -> Status %d (%.3fs)",
                sanitized,
                response.status_code,
                elapsed,
            )
            return response
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            self.logger.error(
                "HTTP Exception: %s failed after %.3fs: %s",
                sanitized,
                elapsed,
                exc,
            )
            raise
