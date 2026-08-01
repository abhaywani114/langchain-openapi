"""Unit tests for AsyncHTTPExecutor, RequestBuilder, and Providers."""

import httpx
import pytest
import respx

from langchain_openapi_tools import (
    APIKeyHeaderProvider,
    APIKeyQueryProvider,
    AsyncHTTPExecutor,
    BasicAuthProvider,
    BearerAuthProvider,
    DataType,
    ExecutionTimeoutError,
    HTTPExecutionError,
    HTTPMethod,
    Operation,
    Parameter,
    ParameterLocation,
    RequestBody,
    RequestValidationError,
    ResponseParser,
    Schema,
)


@pytest.mark.asyncio
@respx.mock
async def test_executor_get_request_with_query_params() -> None:
    """Test GET request execution with path and query parameters."""
    respx.get("https://api.example.com/v1/users/42?rows=5").mock(
        return_value=httpx.Response(200, json={"id": 42, "name": "Alice", "rows": 5})
    )

    op = Operation(
        name="getUser",
        method=HTTPMethod.GET,
        path="/users/{id}",
        parameters=[
            Parameter(
                name="id",
                location=ParameterLocation.PATH,
                required=True,
                schema=Schema(type=DataType.INTEGER),
            ),
            Parameter(
                name="rows",
                location=ParameterLocation.QUERY,
                required=False,
                schema=Schema(type=DataType.INTEGER),
            ),
        ],
    )

    executor = AsyncHTTPExecutor(base_url="https://api.example.com/v1")
    result = await executor.execute(op, {"id": 42, "rows": 5})

    assert result.status_code == 200
    assert result.body == {"id": 42, "name": "Alice", "rows": 5}


@pytest.mark.asyncio
@respx.mock
async def test_executor_post_request_with_json_body() -> None:
    """Test POST request execution with JSON request body."""
    route = respx.post("https://api.example.com/v1/pets").mock(
        return_value=httpx.Response(201, json={"id": 101, "status": "created"})
    )

    op = Operation(
        name="createPet",
        method=HTTPMethod.POST,
        path="/pets",
        request_body=RequestBody(required=True),
    )

    executor = AsyncHTTPExecutor(base_url="https://api.example.com/v1")
    result = await executor.execute(op, {"body": {"name": "Fido", "species": "dog"}})

    assert result.status_code == 201
    assert result.body == {"id": 101, "status": "created"}
    assert route.called
    assert route.calls.last.request.headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_executor_put_and_delete_requests() -> None:
    """Test PUT and DELETE request executions."""
    respx.put("https://api.example.com/v1/items/7").mock(
        return_value=httpx.Response(200, json={"updated": True})
    )
    respx.delete("https://api.example.com/v1/items/7").mock(
        return_value=httpx.Response(204)
    )

    put_op = Operation(
        name="updateItem",
        method=HTTPMethod.PUT,
        path="/items/{id}",
        parameters=[
            Parameter(
                name="id",
                location=ParameterLocation.PATH,
                required=True,
                schema=Schema(type=DataType.INTEGER),
            )
        ],
    )
    del_op = Operation(
        name="deleteItem",
        method=HTTPMethod.DELETE,
        path="/items/{id}",
        parameters=[
            Parameter(
                name="id",
                location=ParameterLocation.PATH,
                required=True,
                schema=Schema(type=DataType.INTEGER),
            )
        ],
    )

    executor = AsyncHTTPExecutor(base_url="https://api.example.com/v1")

    res_put = await executor.execute(put_op, {"id": 7})
    assert res_put.status_code == 200
    assert res_put.body == {"updated": True}

    res_del = await executor.execute(del_op, {"id": 7})
    assert res_del.status_code == 204
    assert res_del.body is None


@pytest.mark.asyncio
@respx.mock
async def test_headers_and_cookies() -> None:
    """Test passing custom headers and cookies."""
    route = respx.get("https://api.example.com/v1/protected").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    op = Operation(
        name="getProtected",
        method=HTTPMethod.GET,
        path="/protected",
        parameters=[
            Parameter(
                name="X-Trace-ID",
                location=ParameterLocation.HEADER,
                required=False,
            ),
            Parameter(
                name="session_token",
                location=ParameterLocation.COOKIE,
                required=False,
            ),
        ],
    )

    executor = AsyncHTTPExecutor(base_url="https://api.example.com/v1")
    await executor.execute(op, {"X-Trace-ID": "trace-12345", "session_token": "abcde"})

    req = route.calls.last.request
    assert req.headers["X-Trace-ID"] == "trace-12345"
    assert "session_token=abcde" in req.headers.get("cookie", "")


@pytest.mark.asyncio
@respx.mock
async def test_authentication_providers() -> None:
    """Test BearerAuthProvider, APIKeyHeaderProvider, and BasicAuthProvider."""
    respx.get("https://api.example.com/bearer").mock(
        return_value=httpx.Response(200, json={"auth": "bearer"})
    )
    respx.get("https://api.example.com/header_key").mock(
        return_value=httpx.Response(200, json={"auth": "header"})
    )
    respx.get("https://api.example.com/query_key?api_key=secret123").mock(
        return_value=httpx.Response(200, json={"auth": "query"})
    )
    respx.get("https://api.example.com/basic").mock(
        return_value=httpx.Response(200, json={"auth": "basic"})
    )

    op_bearer = Operation(name="b", method=HTTPMethod.GET, path="/bearer")
    op_hkey = Operation(name="h", method=HTTPMethod.GET, path="/header_key")
    op_qkey = Operation(name="q", method=HTTPMethod.GET, path="/query_key")
    op_basic = Operation(name="bs", method=HTTPMethod.GET, path="/basic")

    # BearerAuthProvider
    ex_b = AsyncHTTPExecutor(
        base_url="https://api.example.com", provider=BearerAuthProvider("token_abc")
    )
    res = await ex_b.execute(op_bearer, {})
    assert res.body == {"auth": "bearer"}

    # APIKeyHeaderProvider
    ex_h = AsyncHTTPExecutor(
        base_url="https://api.example.com",
        provider=APIKeyHeaderProvider("my_key", header="X-Custom-Key"),
    )
    res = await ex_h.execute(op_hkey, {})
    assert res.body == {"auth": "header"}

    # APIKeyQueryProvider
    ex_q = AsyncHTTPExecutor(
        base_url="https://api.example.com", provider=APIKeyQueryProvider("secret123")
    )
    res = await ex_q.execute(op_qkey, {})
    assert res.body == {"auth": "query"}

    # BasicAuthProvider
    ex_bs = AsyncHTTPExecutor(
        base_url="https://api.example.com",
        provider=BasicAuthProvider("admin", "secret"),
    )
    res = await ex_bs.execute(op_basic, {})
    assert res.body == {"auth": "basic"}


@pytest.mark.asyncio
async def test_missing_path_param_raises_validation_error() -> None:
    """Test missing required path parameter raises RequestValidationError."""
    op = Operation(
        name="getUser",
        method=HTTPMethod.GET,
        path="/users/{id}",
        parameters=[
            Parameter(
                name="id",
                location=ParameterLocation.PATH,
                required=True,
                schema=Schema(type=DataType.INTEGER),
            )
        ],
    )

    executor = AsyncHTTPExecutor(base_url="https://api.example.com")
    with pytest.raises(RequestValidationError) as exc_info:
        await executor.execute(op, {})

    assert "Missing required path parameter 'id'" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_http_404_and_500_responses() -> None:
    """Test 404 and 500 status code responses return ResponseData without crashing."""
    respx.get("https://api.example.com/notfound").mock(
        return_value=httpx.Response(404, json={"error": "Not Found"})
    )
    respx.get("https://api.example.com/servererror").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    op_404 = Operation(name="n404", method=HTTPMethod.GET, path="/notfound")
    op_500 = Operation(name="n500", method=HTTPMethod.GET, path="/servererror")

    executor = AsyncHTTPExecutor(base_url="https://api.example.com")

    r404 = await executor.execute(op_404, {})
    assert r404.status_code == 404
    assert r404.body == {"error": "Not Found"}

    r500 = await executor.execute(op_500, {})
    assert r500.status_code == 500
    assert r500.body == "Internal Server Error"


@pytest.mark.asyncio
@respx.mock
async def test_plain_text_response_fallback() -> None:
    """Test response fallback to plain text when JSON decoding is unavailable."""
    respx.get("https://api.example.com/text").mock(
        return_value=httpx.Response(
            200,
            text="Hello World!",
            headers={"Content-Type": "text/plain"},
        )
    )

    op = Operation(name="getText", method=HTTPMethod.GET, path="/text")
    executor = AsyncHTTPExecutor(base_url="https://api.example.com")

    result = await executor.execute(op, {})
    assert result.status_code == 200
    assert result.body == "Hello World!"


@pytest.mark.asyncio
@respx.mock
async def test_timeout_raises_execution_timeout_error() -> None:
    """Test request timeout raises ExecutionTimeoutError."""
    respx.get("https://api.example.com/slow").mock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )

    op = Operation(name="slowOp", method=HTTPMethod.GET, path="/slow")
    executor = AsyncHTTPExecutor(base_url="https://api.example.com", timeout=1.0)

    with pytest.raises(ExecutionTimeoutError) as exc_info:
        await executor.execute(op, {})

    assert "timed out after 1.0s" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_network_failure_raises_http_execution_error() -> None:
    """Test network failure raises HTTPExecutionError."""
    respx.get("https://api.example.com/fail").mock(
        side_effect=httpx.ConnectError("Failed to connect")
    )

    op = Operation(name="failOp", method=HTTPMethod.GET, path="/fail")
    executor = AsyncHTTPExecutor(base_url="https://api.example.com")

    with pytest.raises(HTTPExecutionError) as exc_info:
        await executor.execute(op, {})

    assert "HTTP request execution failed" in str(exc_info.value)


def test_response_parser_handles_raw_response() -> None:
    """Test ResponseParser directly with mock httpx.Response."""
    raw_res = httpx.Response(200, json={"status": "ok"}, headers={"X-Header": "value"})
    parser = ResponseParser()
    data = parser.parse(raw_res)

    assert data.status_code == 200
    assert data.headers.get("x-header") == "value"
    assert data.body == {"status": "ok"}
    assert data.raw == raw_res
