"""Unit tests for Production Middleware & Resilience system."""

import asyncio
import time
from typing import Any

import httpx
import pytest
import respx

from langchain_openapi_tools import (
    AsyncHTTPExecutor,
    CacheMiddleware,
    HTTPMethod,
    InMemoryCacheBackend,
    LoggingMiddleware,
    Middleware,
    NextCallable,
    OpenAPIToolkit,
    Operation,
    PaginationMiddleware,
    RateLimitMiddleware,
    RetryMiddleware,
)


@pytest.mark.asyncio
@respx.mock
async def test_retry_middleware_on_status_500() -> None:
    """Test RetryMiddleware retries on status 500 and succeeds when server recovers."""
    route = respx.get("https://api.example.com/status").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json={"result": "ok"}),
        ]
    )

    retry_mw = RetryMiddleware(retries=3, backoff="exponential", backoff_factor=0.01)
    executor = AsyncHTTPExecutor(
        base_url="https://api.example.com", middleware=[retry_mw]
    )
    op = Operation(name="getStatus", method=HTTPMethod.GET, path="/status")

    res = await executor.execute(op, {})
    assert res.status_code == 200
    assert res.body == {"result": "ok"}
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_retry_middleware_on_timeout() -> None:
    """Test RetryMiddleware retries network timeout exceptions."""
    route = respx.get("https://api.example.com/timeout").mock(
        side_effect=[
            httpx.ConnectTimeout("Connection timeout"),
            httpx.Response(200, json={"recovered": True}),
        ]
    )

    retry_mw = RetryMiddleware(retries=2, backoff_factor=0.01)
    executor = AsyncHTTPExecutor(
        base_url="https://api.example.com", middleware=[retry_mw]
    )
    op = Operation(name="getTimeout", method=HTTPMethod.GET, path="/timeout")

    res = await executor.execute(op, {})
    assert res.status_code == 200
    assert res.body == {"recovered": True}
    assert route.call_count == 2


def test_retry_backoff_calculation() -> None:
    """Test exponential and fixed backoff calculation."""
    exp_retry = RetryMiddleware(retries=3, backoff="exponential", backoff_factor=0.5)
    assert exp_retry._calculate_delay(1) == 0.5
    assert exp_retry._calculate_delay(2) == 1.0
    assert exp_retry._calculate_delay(3) == 2.0

    fixed_retry = RetryMiddleware(retries=3, backoff="fixed", backoff_factor=1.5)
    assert fixed_retry._calculate_delay(1) == 1.5
    assert fixed_retry._calculate_delay(2) == 1.5


@pytest.mark.asyncio
@respx.mock
async def test_cache_middleware_hit_and_miss() -> None:
    """Test CacheMiddleware caches GET response on hit and misses on new URL."""
    route = respx.get("https://api.example.com/items").mock(
        return_value=httpx.Response(200, json={"items": [1, 2, 3]})
    )

    cache_mw = CacheMiddleware(ttl=60.0)
    executor = AsyncHTTPExecutor(
        base_url="https://api.example.com", middleware=[cache_mw]
    )
    op = Operation(name="getItems", method=HTTPMethod.GET, path="/items")

    # 1. First execution - Cache Miss
    res1 = await executor.execute(op, {})
    assert res1.body == {"items": [1, 2, 3]}
    assert route.call_count == 1

    # 2. Second execution - Cache Hit (no additional HTTP request)
    res2 = await executor.execute(op, {})
    assert res2.body == {"items": [1, 2, 3]}
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_cache_middleware_expiration() -> None:
    """Test CacheMiddleware expires items after TTL."""
    respx.get("https://api.example.com/temp").mock(
        return_value=httpx.Response(200, json={"temp": "value"})
    )

    backend = InMemoryCacheBackend()
    cache_mw = CacheMiddleware(ttl=0.05, backend=backend)
    executor = AsyncHTTPExecutor(
        base_url="https://api.example.com", middleware=[cache_mw]
    )
    op = Operation(name="getTemp", method=HTTPMethod.GET, path="/temp")

    await executor.execute(op, {})
    await asyncio.sleep(0.1)  # Allow TTL to expire

    # Expired request should miss cache and fetch again
    res = await executor.execute(op, {})
    assert res.body == {"temp": "value"}


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_middleware() -> None:
    """Test RateLimitMiddleware throttles execution frequency."""
    respx.get("https://api.example.com/rate").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    rate_mw = RateLimitMiddleware(requests_per_second=10.0)
    rate_mw.tokens = 1.0  # Cap available tokens to force throttling on 2nd call
    executor = AsyncHTTPExecutor(
        base_url="https://api.example.com", middleware=[rate_mw]
    )
    op = Operation(name="getRate", method=HTTPMethod.GET, path="/rate")

    start_time = time.monotonic()
    for _ in range(3):
        await executor.execute(op, {})
    elapsed = time.monotonic() - start_time

    assert elapsed >= 0.1  # Throttled across requests


@pytest.mark.asyncio
@respx.mock
async def test_pagination_middleware() -> None:
    """Test PaginationMiddleware aggregates multi-page results."""
    respx.get("https://api.example.com/users?page=2").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 3}, {"id": 4}]})
    )
    respx.get("https://api.example.com/users").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 1}, {"id": 2}]})
    )

    pag_mw = PaginationMiddleware(max_pages=2)
    executor = AsyncHTTPExecutor(
        base_url="https://api.example.com", middleware=[pag_mw]
    )
    op = Operation(name="getUsers", method=HTTPMethod.GET, path="/users")

    res = await executor.execute(op, {"__paginate__": True})
    assert res.status_code == 200
    assert res.body == {"data": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]}


@pytest.mark.asyncio
async def test_middleware_ordering_and_short_circuit() -> None:
    """Test middleware executes in strict order and can short-circuit pipeline."""
    execution_order: list[str] = []

    class OrderMiddleware1(Middleware):
        async def dispatch(
            self, request: httpx.Request, call_next: NextCallable
        ) -> httpx.Response:
            execution_order.append("MW1_START")
            resp = await call_next(request)
            execution_order.append("MW1_END")
            return resp

    class ShortCircuitMiddleware(Middleware):
        async def dispatch(
            self, request: httpx.Request, call_next: NextCallable
        ) -> httpx.Response:
            execution_order.append("SHORT_CIRCUIT")
            return httpx.Response(200, json={"short_circuit": True})

    class OrderMiddleware2(Middleware):
        async def dispatch(
            self, request: httpx.Request, call_next: NextCallable
        ) -> httpx.Response:
            execution_order.append("MW2_UNREACHABLE")
            return await call_next(request)

    executor = AsyncHTTPExecutor(
        middleware=[
            OrderMiddleware1(),
            ShortCircuitMiddleware(),
            OrderMiddleware2(),
        ]
    )
    op = Operation(name="getShort", method=HTTPMethod.GET, path="/short")

    res = await executor.execute(op, {})
    assert res.body == {"short_circuit": True}
    assert execution_order == ["MW1_START", "SHORT_CIRCUIT", "MW1_END"]


def test_toolkit_middleware_registration() -> None:
    """Test OpenAPIToolkit registers middleware sequence cleanly."""
    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "ping",
                    "responses": {"200": {"description": "Pong"}},
                }
            }
        },
    }

    mw_list = [
        LoggingMiddleware(),
        RetryMiddleware(),
        CacheMiddleware(),
    ]
    toolkit = OpenAPIToolkit.from_dict(spec_dict, middleware=mw_list)
    assert toolkit.executor.pipeline.middlewares == mw_list
