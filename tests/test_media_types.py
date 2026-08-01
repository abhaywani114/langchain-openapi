"""Tests for the media-type-aware request builder pipeline.

Verifies that ``RequestBuilder`` chooses the right transport surface based
on the request body's declared content type:

* ``application/json`` and ``+json`` variants → ``json_body``.
* ``application/x-www-form-urlencoded`` → ``data``.
* ``multipart/form-data`` → ``files`` (with regular form fields wrapped
  in ``(None, value)`` tuples per httpx conventions).
* ``text/plain`` / ``application/xml`` → ``content``.
* Unknown content types default to ``json_body``.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from langchain_openapi_tools import (
    AsyncHTTPExecutor,
    HTTPMethod,
    MediaType,
    Operation,
    RequestBody,
    RequestBuilder,
    Schema,
)
from langchain_openapi_tools.enums import DataType


def _op(request_body: RequestBody) -> Operation:
    return Operation(
        name="submit",
        method=HTTPMethod.POST,
        path="/submit",
        request_body=request_body,
    )


def test_builder_json_body_default() -> None:
    op = _op(
        RequestBody(
            required=True,
            content={
                "application/json": MediaType(
                    content_type="application/json",
                    schema=Schema(type=DataType.OBJECT),
                )
            },
        )
    )
    built = RequestBuilder(base_url="https://api.example.com").build(
        op, {"body": {"hello": "world"}}
    )
    assert built.json_body == {"hello": "world"}
    assert built.data is None
    assert built.files is None
    assert built.headers.get("Content-Type") == "application/json"


def test_builder_urlencoded_body_uses_data() -> None:
    op = _op(
        RequestBody(
            required=True,
            content={
                "application/x-www-form-urlencoded": MediaType(
                    content_type="application/x-www-form-urlencoded"
                )
            },
        )
    )
    built = RequestBuilder(base_url="https://api.example.com").build(
        op, {"body": {"username": "alice", "password": "hunter2"}}
    )
    assert built.data == {"username": "alice", "password": "hunter2"}
    assert built.json_body is None
    assert built.files is None
    assert built.headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_builder_multipart_body_uses_files() -> None:
    op = _op(
        RequestBody(
            required=True,
            content={
                "multipart/form-data": MediaType(content_type="multipart/form-data")
            },
        )
    )
    built = RequestBuilder(base_url="https://api.example.com").build(
        op, {"body": {"file": b"binary-payload", "note": "hi"}}
    )
    assert built.files is not None
    assert "file" in built.files
    assert "note" in built.files
    # httpx will inject its own multipart Content-Type + boundary.
    assert "Content-Type" not in built.headers


def test_builder_plain_text_body_uses_content() -> None:
    op = _op(
        RequestBody(
            required=True,
            content={"text/plain": MediaType(content_type="text/plain")},
        )
    )
    built = RequestBuilder(base_url="https://api.example.com").build(
        op, {"body": "raw string payload"}
    )
    assert built.content == "raw string payload"
    assert built.headers["Content-Type"] == "text/plain"


def test_builder_xml_body_uses_content() -> None:
    op = _op(
        RequestBody(
            required=True,
            content={"application/xml": MediaType(content_type="application/xml")},
        )
    )
    built = RequestBuilder(base_url="https://api.example.com").build(
        op, {"body": "<x/>"}
    )
    assert built.content == "<x/>"
    assert built.headers["Content-Type"] == "application/xml"


def test_builder_json_variant_content_type_still_json() -> None:
    op = _op(
        RequestBody(
            required=True,
            content={
                "application/vnd.api+json": MediaType(
                    content_type="application/vnd.api+json"
                )
            },
        )
    )
    built = RequestBuilder(base_url="https://api.example.com").build(
        op, {"body": {"foo": 1}}
    )
    assert built.json_body == {"foo": 1}
    assert built.headers.get("Content-Type") == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_executor_sends_urlencoded_body_over_wire() -> None:
    route = respx.post("https://api.example.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "x"})
    )
    op = Operation(
        name="token",
        method=HTTPMethod.POST,
        path="/token",
        request_body=RequestBody(
            required=True,
            content={
                "application/x-www-form-urlencoded": MediaType(
                    content_type="application/x-www-form-urlencoded"
                )
            },
        ),
    )
    executor = AsyncHTTPExecutor(base_url="https://api.example.com")
    result = await executor.execute(
        op, {"body": {"grant_type": "password", "username": "u", "password": "p"}}
    )
    assert result.status_code == 200
    sent = route.calls.last.request
    assert (
        sent.headers["Content-Type"].startswith(
            "application/x-www-form-urlencoded"
        )
    )
    assert b"grant_type=password" in sent.content


@pytest.mark.asyncio
@respx.mock
async def test_executor_sends_multipart_body_over_wire() -> None:
    route = respx.post("https://api.example.com/upload").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    op = Operation(
        name="upload",
        method=HTTPMethod.POST,
        path="/upload",
        request_body=RequestBody(
            required=True,
            content={
                "multipart/form-data": MediaType(content_type="multipart/form-data")
            },
        ),
    )
    executor = AsyncHTTPExecutor(base_url="https://api.example.com")
    result = await executor.execute(
        op, {"body": {"file": b"hello", "name": "greeting.txt"}}
    )
    assert result.status_code == 200
    sent = route.calls.last.request
    assert sent.headers["Content-Type"].startswith("multipart/form-data")
    assert b"hello" in sent.content
