"""Unit tests for Authentication & Request Providers system."""

from typing import Any

import httpx
import pytest
import respx

from langchain_openapi_tools import (
    APIKeyHeaderProvider,
    APIKeyQueryProvider,
    AsyncHTTPExecutor,
    AuthenticationError,
    BasicAuthProvider,
    BearerAuthProvider,
    CompositeProvider,
    CookiesProvider,
    HTTPMethod,
    OpenAPIToolkit,
    Operation,
    ProviderError,
    RequestProvider,
    StaticHeadersProvider,
)
from langchain_openapi_tools.utils import sanitize_request_log


@pytest.mark.asyncio
async def test_bearer_auth_provider() -> None:
    """Test BearerAuthProvider injects Authorization Bearer header."""
    provider = BearerAuthProvider(token="my_jwt_token")
    req = httpx.Request("GET", "https://api.example.com/data")

    res_req = await provider.apply(req)
    assert res_req.headers["Authorization"] == "Bearer my_jwt_token"

    with pytest.raises(AuthenticationError):
        BearerAuthProvider(token="   ")


@pytest.mark.asyncio
async def test_basic_auth_provider() -> None:
    """Test BasicAuthProvider injects base64-encoded Authorization header."""
    provider = BasicAuthProvider(username="admin", password="secret_pass")
    req = httpx.Request("GET", "https://api.example.com/data")

    res_req = await provider.apply(req)
    assert res_req.headers["Authorization"] == "Basic YWRtaW46c2VjcmV0X3Bhc3M="


@pytest.mark.asyncio
async def test_api_key_header_provider() -> None:
    """Test APIKeyHeaderProvider injects key into custom header."""
    provider = APIKeyHeaderProvider(key="key_123", header="X-Custom-Key")
    req = httpx.Request("GET", "https://api.example.com/data")

    res_req = await provider.apply(req)
    assert res_req.headers["X-Custom-Key"] == "key_123"

    with pytest.raises(AuthenticationError):
        APIKeyHeaderProvider(key="", header="X-Key")


@pytest.mark.asyncio
async def test_api_key_query_provider() -> None:
    """Test APIKeyQueryProvider appends key into query parameters."""
    provider = APIKeyQueryProvider(key="secret_key", parameter="api_key")
    req = httpx.Request("GET", "https://api.example.com/data?query=test")

    res_req = await provider.apply(req)
    assert (
        str(res_req.url) == "https://api.example.com/data?query=test&api_key=secret_key"
    )

    with pytest.raises(AuthenticationError):
        APIKeyQueryProvider(key="abc", parameter="")


@pytest.mark.asyncio
async def test_static_headers_provider() -> None:
    """Test StaticHeadersProvider injects arbitrary key-value headers."""
    provider = StaticHeadersProvider(
        {"User-Agent": "langchain-openapi/1.0", "X-App-ID": "app_99"}
    )
    req = httpx.Request("GET", "https://api.example.com/data")

    res_req = await provider.apply(req)
    assert res_req.headers["User-Agent"] == "langchain-openapi/1.0"
    assert res_req.headers["X-App-ID"] == "app_99"


@pytest.mark.asyncio
async def test_cookies_provider() -> None:
    """Test CookiesProvider injects and merges Cookie header pairs."""
    provider = CookiesProvider({"session": "sess_abc", "theme": "dark"})
    req = httpx.Request(
        "GET",
        "https://api.example.com/data",
        headers={"Cookie": "existing=val"},
    )

    res_req = await provider.apply(req)
    cookie_hdr = res_req.headers["Cookie"]
    assert "existing=val" in cookie_hdr
    assert "session=sess_abc" in cookie_hdr
    assert "theme=dark" in cookie_hdr


@pytest.mark.asyncio
@respx.mock
async def test_composite_provider_and_execution_order() -> None:
    """Test CompositeProvider executes providers sequentially in order."""
    route = respx.get("https://api.example.com/v1/resource?api_key=secret_key").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    composite = CompositeProvider(
        [
            BearerAuthProvider(token="jwt_token_123"),
            APIKeyQueryProvider(key="secret_key", parameter="api_key"),
            StaticHeadersProvider({"X-Trace": "trace_001"}),
            CookiesProvider({"user_session": "s_123"}),
        ]
    )

    executor = AsyncHTTPExecutor(
        base_url="https://api.example.com/v1", provider=composite
    )
    op = Operation(name="getResource", method=HTTPMethod.GET, path="/resource")

    result = await executor.execute(op, {})
    assert result.status_code == 200
    assert result.body == {"status": "ok"}

    assert route.called
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer jwt_token_123"
    assert req.headers["X-Trace"] == "trace_001"
    assert "user_session=s_123" in req.headers["Cookie"]


@pytest.mark.asyncio
async def test_composite_provider_error_propagation() -> None:
    """Test CompositeProvider propagates AuthenticationError and ProviderError."""

    class FaultyProvider(RequestProvider):
        async def apply(self, request: httpx.Request) -> httpx.Request:
            raise ValueError("Simulated provider error")

    composite = CompositeProvider([FaultyProvider()])
    req = httpx.Request("GET", "https://api.example.com")

    with pytest.raises(ProviderError) as exc_info:
        await composite.apply(req)

    assert "Request provider execution failed" in str(exc_info.value)

    with pytest.raises(ProviderError):
        CompositeProvider("invalid_type")  # type: ignore[arg-type]


def test_toolkit_integration_with_providers() -> None:
    """Test OpenAPIToolkit integrates with CompositeProvider and built-in providers."""
    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/data": {
                "get": {
                    "operationId": "getData",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    provider = CompositeProvider(
        [
            BearerAuthProvider(token="my_token"),
            StaticHeadersProvider({"X-Source": "ToolkitTest"}),
        ]
    )

    toolkit = OpenAPIToolkit.from_dict(spec_dict, provider=provider)
    assert toolkit.executor.provider == provider


def test_log_sanitization() -> None:
    """Test sanitize_request_log redacts sensitive token/key parameters."""
    url = (
        "https://api.example.com/v1/query?api_key=secret_12345&token=jwt_999&user=alice"
    )
    sanitized = sanitize_request_log("GET", url)

    assert "secret_12345" not in sanitized
    assert "jwt_999" not in sanitized
    assert "api_key=[REDACTED]" in sanitized
    assert "token=[REDACTED]" in sanitized
    assert "user=alice" in sanitized
    assert sanitized.startswith("GET 'https://api.example.com")
