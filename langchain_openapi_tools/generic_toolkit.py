"""Generic HTTP Toolkit for large OpenAPI surfaces.

Where :class:`~langchain_openapi_tools.toolkit.OpenAPIToolkit` generates one
LangChain tool per operation (great for small/medium APIs), the Generic
Toolkit exposes a small, fixed set of HTTP tools plus endpoint-discovery
helpers regardless of how many operations the underlying spec contains.

The two toolkits share the entire execution stack — loader, parser,
resolver, authentication, middleware, executor, response parser — and
differ only in the LangChain interface presented to the agent.

Typical reasoning flow with the Generic Toolkit::

    user -> search_operations("books")
         -> describe_operation("get_books")
         -> GET(endpoint="/books", params={...})
         -> response

Hybrid mode combines typed and generic tools: typed tools are emitted for
a curated subset of operations (via ``typed_tags`` or ``typed_operations``)
while the rest of the API is reachable through the generic HTTP tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from langchain_openapi_tools.exceptions import HTTPExecutionError
from langchain_openapi_tools.executor import AsyncHTTPExecutor
from langchain_openapi_tools.loader import OpenAPILoader
from langchain_openapi_tools.middleware import Middleware
from langchain_openapi_tools.models import Operation
from langchain_openapi_tools.parser import OpenAPIParser, OpenAPISpec
from langchain_openapi_tools.providers import RequestProvider
from langchain_openapi_tools.search import OperationEntry, OperationIndex
from langchain_openapi_tools.toolkit import (
    LangChainToolFactory,
    OpenAPIToolkitConfig,
    filter_operations,
    format_tool_name,
)

logger = logging.getLogger(__name__)

ToolkitMode = Literal["typed", "generic", "hybrid"]


# =========================================================================
# Pydantic argument schemas for the generic tools
# =========================================================================


class _HTTPBaseArgs(BaseModel):
    """Base schema shared by every generic HTTP tool."""

    endpoint: str = Field(
        ...,
        description=(
            "API path or absolute URL to call, e.g. '/pets/1' or "
            "'/books?limit=10'. Path parameters must already be substituted."
        ),
    )
    params: dict[str, Any] | None = Field(
        default=None, description="Optional query string parameters."
    )
    headers: dict[str, Any] | None = Field(
        default=None, description="Optional HTTP headers to send with the request."
    )


class _HTTPGetArgs(_HTTPBaseArgs):
    """Arguments for the generic ``GET`` tool."""


class _HTTPDeleteArgs(_HTTPBaseArgs):
    """Arguments for the generic ``DELETE`` tool."""


class _HTTPWriteArgs(_HTTPBaseArgs):
    """Arguments shared by ``POST`` / ``PUT`` / ``PATCH``."""

    body: Any = Field(
        default=None,
        description="Optional JSON request body to send with the request.",
    )


class _HTTPPostArgs(_HTTPWriteArgs):
    """Arguments for the generic ``POST`` tool."""


class _HTTPPutArgs(_HTTPWriteArgs):
    """Arguments for the generic ``PUT`` tool."""


class _HTTPPatchArgs(_HTTPWriteArgs):
    """Arguments for the generic ``PATCH`` tool."""


class _SearchOperationsArgs(BaseModel):
    """Arguments for ``search_operations``."""

    query: str = Field(..., description="Natural-language search query.")
    limit: int = Field(
        default=10, ge=1, le=100, description="Maximum number of matches to return."
    )
    tag: str | None = Field(
        default=None, description="Optional tag to constrain the search."
    )
    method: str | None = Field(
        default=None,
        description="Optional HTTP method filter (GET, POST, PUT, PATCH, DELETE).",
    )


class _DescribeOperationArgs(BaseModel):
    """Arguments for ``describe_operation``."""

    operation_id: str = Field(
        ...,
        description=(
            "Canonical operation id, OpenAPI operationId, or 'METHOD /path' key."
        ),
    )


class _ListOperationsArgs(BaseModel):
    """Arguments for ``list_operations``."""

    tag: str | None = Field(
        default=None, description="Optional tag filter."
    )
    method: str | None = Field(
        default=None, description="Optional HTTP method filter."
    )
    limit: int = Field(
        default=100, ge=1, le=1000, description="Maximum number of items to return."
    )


class _ListTagsArgs(BaseModel):
    """Arguments for ``list_tags``. Takes no fields but must be a model."""


# =========================================================================
# Generic HTTP tool factory
# =========================================================================


def _summarize_entry(entry: OperationEntry) -> dict[str, Any]:
    """Compact projection of an :class:`OperationEntry` for discovery output."""
    return {
        "operation_id": entry.canonical_id,
        "method": entry.method,
        "path": entry.path,
        "summary": entry.summary,
        "tags": list(entry.tags),
    }


def _describe_entry(entry: OperationEntry) -> dict[str, Any]:
    """Full projection of an operation for ``describe_operation``."""
    op = entry.operation
    payload: dict[str, Any] = {
        "operation_id": entry.canonical_id,
        "method": entry.method,
        "path": entry.path,
        "summary": entry.summary,
        "description": entry.description,
        "tags": list(entry.tags),
    }
    if op is None:
        return payload

    parameters: list[dict[str, Any]] = []
    for param in op.parameters:
        schema_type: Any = None
        if param.schema is not None:
            schema_type = param.schema.type
            if hasattr(schema_type, "value"):
                schema_type = schema_type.value
        parameters.append(
            {
                "name": param.name,
                "in": param.location.value,
                "required": param.required,
                "description": param.description,
                "type": schema_type,
            }
        )
    payload["parameters"] = parameters

    if op.request_body is not None:
        media_types = list((op.request_body.content or {}).keys())
        payload["request_body"] = {
            "required": op.request_body.required,
            "description": op.request_body.description,
            "media_types": media_types,
        }

    if op.responses:
        payload["responses"] = {
            status: {
                "description": resp.description,
                "media_types": list((resp.content or {}).keys()),
            }
            for status, resp in op.responses.items()
        }

    if op.deprecated:
        payload["deprecated"] = True

    return payload


class GenericHTTPToolFactory:
    """Builds the fixed set of LangChain tools exposed by the Generic Toolkit.

    The factory reuses a caller-supplied :class:`AsyncHTTPExecutor` so
    provider, middleware, timeout, and caching behaviour are identical to
    the typed toolkit.
    """

    def __init__(
        self,
        executor: AsyncHTTPExecutor,
        index: OperationIndex,
    ) -> None:
        self.executor = executor
        self.index = index

    # ---------------------------------------------------------------- HTTP

    def _make_http_tool(
        self,
        method: str,
        args_model: type[BaseModel],
        supports_body: bool,
    ) -> StructuredTool:
        method_upper = method.upper()
        executor = self.executor

        async def _arun(**kwargs: Any) -> Any:
            endpoint = kwargs.get("endpoint")
            if not endpoint:
                raise ToolException(
                    f"{method_upper} requires an 'endpoint' argument."
                )
            params = kwargs.get("params") or None
            headers = kwargs.get("headers") or None
            body = kwargs.get("body") if supports_body else None
            try:
                result = await executor.request(
                    method=method_upper,
                    endpoint=endpoint,
                    params=params,
                    headers=headers,
                    json_body=body,
                )
                if result.status_code >= 400:
                    raise ToolException(
                        f"HTTP {method_upper} request failed with status "
                        f"{result.status_code}: {result.body}"
                    )
                return result.body
            except ToolException:
                raise
            except HTTPExecutionError as exc:
                raise ToolException(f"API execution error: {exc}") from exc
            except Exception as exc:
                raise ToolException(f"Tool execution error: {exc}") from exc

        def _run(**kwargs: Any) -> Any:
            return _sync_from_async(_arun, kwargs)

        description_lines = [
            f"Execute an HTTP {method_upper} request against the target API.",
            (
                "Use search_operations() and describe_operation() first to "
                "discover the correct endpoint, parameters, and expected "
                "response schema."
            ),
        ]
        if supports_body:
            description_lines.append(
                "Provide the JSON payload via the 'body' argument."
            )

        return StructuredTool.from_function(
            func=_run,
            coroutine=_arun,
            name=method_upper,
            description="\n".join(description_lines),
            args_schema=args_model,
            metadata={"generic": True, "method": method_upper},
            handle_tool_error=True,
        )

    def get_tool(self) -> StructuredTool:  # pragma: no cover - convenience alias
        return self._make_http_tool("GET", _HTTPGetArgs, supports_body=False)

    def http_tools(self) -> list[StructuredTool]:
        """Return the five generic HTTP tools: GET, POST, PUT, PATCH, DELETE."""
        return [
            self._make_http_tool("GET", _HTTPGetArgs, supports_body=False),
            self._make_http_tool("POST", _HTTPPostArgs, supports_body=True),
            self._make_http_tool("PUT", _HTTPPutArgs, supports_body=True),
            self._make_http_tool("PATCH", _HTTPPatchArgs, supports_body=True),
            self._make_http_tool("DELETE", _HTTPDeleteArgs, supports_body=False),
        ]

    # ---------------------------------------------------------- Discovery

    def discovery_tools(self) -> list[StructuredTool]:
        """Return endpoint discovery tools backed by :class:`OperationIndex`."""
        index = self.index

        def _search(**kwargs: Any) -> Any:
            query = kwargs.get("query", "")
            limit = kwargs.get("limit", 10)
            tag = kwargs.get("tag")
            method = kwargs.get("method")
            results = index.search(
                query=query, limit=limit, tag=tag, method=method
            )
            return [r.to_dict() for r in results]

        def _describe(**kwargs: Any) -> Any:
            op_id = kwargs.get("operation_id", "")
            entry = index.get(op_id)
            if entry is None:
                raise ToolException(
                    f"No operation found for id '{op_id}'. "
                    "Try search_operations() to discover valid ids."
                )
            return _describe_entry(entry)

        def _list_ops(**kwargs: Any) -> Any:
            tag = kwargs.get("tag")
            method = kwargs.get("method")
            limit = kwargs.get("limit", 100)
            entries = index.list_entries(tag=tag, method=method)
            return [_summarize_entry(e) for e in entries[:limit]]

        def _list_tags(**_: Any) -> Any:
            return index.tags()

        search_tool = StructuredTool.from_function(
            func=_search,
            name="search_operations",
            description=(
                "Search the API's operations by keyword. Returns a ranked "
                "list of {operation_id, method, path, summary, tags} objects. "
                "Call this before invoking GET/POST/etc. so the agent knows "
                "which endpoint to hit."
            ),
            args_schema=_SearchOperationsArgs,
            metadata={"generic": True, "kind": "discovery"},
            handle_tool_error=True,
        )
        describe_tool = StructuredTool.from_function(
            func=_describe,
            name="describe_operation",
            description=(
                "Return the summary, description, parameters, request body, "
                "and responses for a specific operation. Use the "
                "operation_id returned by search_operations()."
            ),
            args_schema=_DescribeOperationArgs,
            metadata={"generic": True, "kind": "discovery"},
            handle_tool_error=True,
        )
        list_ops_tool = StructuredTool.from_function(
            func=_list_ops,
            name="list_operations",
            description=(
                "List all operations available on the API, optionally "
                "filtered by tag or HTTP method."
            ),
            args_schema=_ListOperationsArgs,
            metadata={"generic": True, "kind": "discovery"},
            handle_tool_error=True,
        )
        list_tags_tool = StructuredTool.from_function(
            func=_list_tags,
            name="list_tags",
            description="List all tags declared by the API.",
            args_schema=_ListTagsArgs,
            metadata={"generic": True, "kind": "discovery"},
            handle_tool_error=True,
        )

        return [search_tool, describe_tool, list_ops_tool, list_tags_tool]

    def all_tools(self) -> list[StructuredTool]:
        """Return the full generic toolset: HTTP tools + discovery tools."""
        return self.http_tools() + self.discovery_tools()


def _sync_from_async(coro_fn: Any, kwargs: dict[str, Any]) -> Any:
    """Run an async tool implementation from a sync context safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: asyncio.run(coro_fn(**kwargs)))
            return future.result()
    return asyncio.run(coro_fn(**kwargs))


# =========================================================================
# GenericOpenAPIToolkit
# =========================================================================


@dataclass
class GenericToolkitConfig:
    """Optional configuration for :class:`GenericOpenAPIToolkit`.

    Attributes:
        include_http_methods: HTTP methods to expose as generic tools.
        include_discovery_tools: Whether to expose the discovery helpers.
        typed_tags: In hybrid mode, only operations with any of these tags
            become typed tools; everything else is served by the generic
            HTTP tools.
        typed_operations: In hybrid mode, additional operation ids that
            should be exposed as typed tools regardless of tag.
        typed_config: Optional configuration passed to the typed toolkit
            factory for description formatting, name overrides, etc.
    """

    include_http_methods: Sequence[str] = field(
        default_factory=lambda: ("GET", "POST", "PUT", "PATCH", "DELETE")
    )
    include_discovery_tools: bool = True
    typed_tags: list[str] | None = None
    typed_operations: list[str] | None = None
    typed_config: OpenAPIToolkitConfig | None = None


class GenericOpenAPIToolkit:
    """Toolkit exposing a small, fixed set of HTTP + discovery tools.

    The Generic Toolkit is designed for large OpenAPI surfaces where
    generating one typed tool per operation would blow the prompt / context
    window. It reuses the same loader, parser, provider, middleware, and
    executor as :class:`~langchain_openapi_tools.toolkit.OpenAPIToolkit`,
    only differing in the LangChain interface it emits.

    Modes exposed via :meth:`get_tools`:

    * ``"generic"`` — five HTTP tools (GET/POST/PUT/PATCH/DELETE) plus four
      discovery helpers (``search_operations``, ``describe_operation``,
      ``list_operations``, ``list_tags``).
    * ``"typed"`` — one typed tool per operation, identical to the classic
      :class:`OpenAPIToolkit` output.
    * ``"hybrid"`` — typed tools for operations selected via ``typed_tags``
      or ``typed_operations``, plus the generic tools for everything else.
    """

    def __init__(
        self,
        spec: OpenAPISpec,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: GenericToolkitConfig | None = None,
    ) -> None:
        self.spec = spec
        self.config = config or GenericToolkitConfig()

        effective_base_url = base_url
        if not effective_base_url and spec.servers:
            effective_base_url = spec.servers[0]

        self.executor = AsyncHTTPExecutor(
            base_url=effective_base_url,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
        )

        parser = OpenAPIParser(spec)
        self._operations: list[Operation] = parser.parse()
        self.index = OperationIndex(self._operations)

        self._typed_factory = LangChainToolFactory(
            executor=self.executor,
            config=self.config.typed_config or OpenAPIToolkitConfig(),
        )
        self._generic_factory = GenericHTTPToolFactory(
            executor=self.executor,
            index=self.index,
        )

        logger.info(
            "GenericOpenAPIToolkit initialised (%d operations indexed).",
            len(self._operations),
        )

    # ------------------------------------------------------------ Factories

    @classmethod
    def from_url(
        cls,
        url: str,
        headers: dict[str, str] | None = None,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: GenericToolkitConfig | None = None,
    ) -> GenericOpenAPIToolkit:
        loader = OpenAPILoader.from_url(url, headers=headers)
        spec = loader.load()
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
        )

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: GenericToolkitConfig | None = None,
    ) -> GenericOpenAPIToolkit:
        loader = OpenAPILoader.from_file(file_path)
        spec = loader.load()
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
        )

    @classmethod
    def from_dict(
        cls,
        spec_dict: dict[str, Any],
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: GenericToolkitConfig | None = None,
    ) -> GenericOpenAPIToolkit:
        loader = OpenAPILoader.from_dict(spec_dict)
        spec = loader.load()
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
        )

    @classmethod
    def from_spec(
        cls,
        spec: OpenAPISpec,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: GenericToolkitConfig | None = None,
    ) -> GenericOpenAPIToolkit:
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
        )

    # ------------------------------------------------------------ Public API

    def get_tools(
        self,
        mode: ToolkitMode = "generic",
        typed_tags: list[str] | None = None,
        typed_operations: list[str] | None = None,
    ) -> list[BaseTool]:
        """Return the tools for the requested execution strategy.

        Args:
            mode: ``"typed"``, ``"generic"``, or ``"hybrid"``.
            typed_tags: Overrides ``config.typed_tags`` when provided.
                Only used in ``hybrid`` mode.
            typed_operations: Overrides ``config.typed_operations`` when
                provided. Only used in ``hybrid`` mode.

        Returns:
            List of LangChain :class:`BaseTool` instances.
        """
        if mode == "typed":
            return self._build_typed_tools(self._operations)

        if mode == "generic":
            tools: list[BaseTool] = list(self._filter_http_tools())
            if self.config.include_discovery_tools:
                tools.extend(self._generic_factory.discovery_tools())
            return tools

        if mode == "hybrid":
            selected_tags = typed_tags or self.config.typed_tags or []
            selected_ops = typed_operations or self.config.typed_operations or []
            typed_ops = self._select_typed_operations(selected_tags, selected_ops)
            typed_tools = self._build_typed_tools(typed_ops)
            generic_http = list(self._filter_http_tools())
            discovery = (
                self._generic_factory.discovery_tools()
                if self.config.include_discovery_tools
                else []
            )
            return typed_tools + generic_http + discovery

        raise ValueError(
            f"Unknown toolkit mode {mode!r}. Expected 'typed', 'generic', "
            "or 'hybrid'."
        )

    def list_operations(self) -> list[dict[str, Any]]:
        """Return the compact list of operations known to the toolkit."""
        return [_summarize_entry(e) for e in self.index.entries]

    def search_operations(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Programmatic hook mirroring the ``search_operations`` tool."""
        return [r.to_dict() for r in self.index.search(query=query, limit=limit)]

    def describe_operation(self, operation_id: str) -> dict[str, Any]:
        """Programmatic hook mirroring the ``describe_operation`` tool."""
        entry = self.index.get(operation_id)
        if entry is None:
            raise KeyError(f"Unknown operation id: {operation_id!r}")
        return _describe_entry(entry)

    def list_tags(self) -> list[str]:
        """Programmatic hook mirroring the ``list_tags`` tool."""
        return self.index.tags()

    # ------------------------------------------------------------ Internals

    def _filter_http_tools(self) -> list[StructuredTool]:
        enabled = {m.upper() for m in self.config.include_http_methods}
        return [
            tool
            for tool in self._generic_factory.http_tools()
            if tool.name.upper() in enabled
        ]

    def _select_typed_operations(
        self,
        tags: list[str],
        operation_ids: list[str],
    ) -> list[Operation]:
        if not tags and not operation_ids:
            return []
        tag_set = set(tags)
        op_set = set(operation_ids)
        selected: list[Operation] = []
        for op in self._operations:
            candidate_names = {op.name, format_tool_name(op)}
            if op.operation_id:
                candidate_names.add(op.operation_id)
            if op_set and (candidate_names & op_set):
                selected.append(op)
                continue
            if tag_set and any(t in tag_set for t in op.tags):
                selected.append(op)
        return selected

    def _build_typed_tools(self, operations: list[Operation]) -> list[BaseTool]:
        cfg = self.config.typed_config or OpenAPIToolkitConfig()
        filtered = filter_operations(operations, cfg)
        tools: list[BaseTool] = []
        used_names: set[str] = set()
        for op in filtered:
            base_name = format_tool_name(op)
            candidate = base_name
            counter = 2
            while candidate in used_names:
                candidate = f"{base_name}_{counter}"
                counter += 1
            used_names.add(candidate)
            tools.append(
                self._typed_factory.create_tool(op, name_override=candidate)
            )
        return tools


__all__ = [
    "GenericHTTPToolFactory",
    "GenericOpenAPIToolkit",
    "GenericToolkitConfig",
    "ToolkitMode",
]


# Re-export json for downstream callers that may want to serialise tool
# metadata to strings. Keeps this module self-contained.
_ = json
