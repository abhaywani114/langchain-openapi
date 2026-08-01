"""OpenAPIToolkit for loading specifications and managing LangChain tools."""

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import BaseTool, StructuredTool, ToolException

from langchain_openapi_tools.exceptions import HTTPExecutionError
from langchain_openapi_tools.executor import AsyncHTTPExecutor
from langchain_openapi_tools.loader import OpenAPILoader
from langchain_openapi_tools.middleware import Middleware
from langchain_openapi_tools.models import Operation
from langchain_openapi_tools.parser import OpenAPIParser, OpenAPISpec
from langchain_openapi_tools.providers import RequestProvider
from langchain_openapi_tools.schema_converter import SchemaConverter

logger = logging.getLogger(__name__)


@dataclass
class OpenAPIToolkitConfig:
    """Configuration settings for tool generation and prompt optimization."""

    description_mode: Literal["full", "compact", "minimal"] = "full"
    compress_descriptions: bool = False
    include_tags: list[str] | None = None
    exclude_tags: list[str] | None = None
    include_operations: list[str] | None = None
    exclude_operations: list[str] | None = None
    tool_description_overrides: dict[str, str] | None = None
    description_builder: Callable[[Operation], str] | None = None


class OpenAPIToolCallbackHandler(BaseCallbackHandler):
    """Callback handler for logging OpenAPI tool execution lifecycle events."""

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "OpenAPITool")
        logger.info(
            "Starting execution of OpenAPI tool '%s' with input: %s",
            tool_name,
            input_str,
        )

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        logger.info("Successfully finished execution of OpenAPI tool.")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        logger.error("OpenAPI tool execution failed with error: %s", error)


def format_tool_name(operation: Operation) -> str:
    """Format an operation into a clean snake_case tool name."""
    if operation.operation_id:
        raw_name = operation.operation_id
    elif operation.summary:
        raw_name = operation.summary
    else:
        raw_name = operation.name

    clean = re.sub(r"[^\w\s-]", "", raw_name)
    clean = re.sub(r"[\s-]+", "_", clean)
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", clean)
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    final_name = re.sub(r"_+", "_", snake).strip("_")

    return final_name if final_name else "openapi_tool"


def compress_description_text(text: str, operation: Operation) -> str:
    """Compress description by removing duplicated text and whitespace."""
    lines = [line.strip() for line in text.splitlines()]
    unique_lines: list[str] = []
    seen: set[str] = set()

    for line in lines:
        if not line:
            continue
        normalized = line.lower()
        if normalized in seen:
            continue
        if operation.summary and operation.description:
            summary_clean = operation.summary.strip().lower()
            if normalized == summary_clean and any(
                s.lower() == summary_clean for s in seen
            ):
                continue
        seen.add(normalized)
        unique_lines.append(line)

    return "\n".join(unique_lines)


def build_tool_description(
    operation: Operation,
    tool_name: str | None = None,
    config: OpenAPIToolkitConfig | None = None,
) -> str:
    """Build a human-readable description for an operation tool."""
    if config is None:
        config = OpenAPIToolkitConfig()

    op_keys = [operation.name]
    if operation.operation_id:
        op_keys.append(operation.operation_id)
    if tool_name:
        op_keys.append(tool_name)

    # 1. Custom description overrides
    if config.tool_description_overrides:
        for key in op_keys:
            if key in config.tool_description_overrides:
                return config.tool_description_overrides[key]

    # 2. Custom builder callback
    if config.description_builder is not None:
        return config.description_builder(operation)

    # 3. Description modes
    mode = config.description_mode

    if mode == "minimal":
        first_sentence = ""
        if operation.summary:
            first_sentence = operation.summary.strip()
        elif operation.description:
            first_sentence = operation.description.strip().split(".")[0]
        else:
            first_sentence = operation.name.replace("_", " ").title()

        if not first_sentence.endswith("."):
            first_sentence += "."
        return first_sentence

    parts: list[str] = []

    if mode == "compact":
        summary_clean = (operation.summary or operation.description or "").strip()
        if summary_clean:
            first_line = summary_clean.split("\n")[0].strip()
            if not first_line.endswith("."):
                first_line += "."
            parts.append(first_line)
        else:
            parts.append(f"Execute {operation.method.value.upper()} operation.")

        if operation.parameters:
            param_strings = [
                f"{p.name} ({p.location.value}{', required' if p.required else ''})"
                for p in operation.parameters
            ]
            parts.append(f"Parameters: {', '.join(param_strings)}")

    else:  # "full" mode
        if operation.summary:
            summary_clean = operation.summary.strip()
            if not summary_clean.endswith("."):
                summary_clean += "."
            parts.append(summary_clean)

        if operation.description:
            parts.append(operation.description.strip())

        parts.append(f"HTTP Method: {operation.method.value.upper()}")
        parts.append(f"Path: {operation.path}")

    description_text = "\n\n".join(parts)

    if config.compress_descriptions:
        description_text = compress_description_text(description_text, operation)

    return description_text


def filter_operations(
    operations: list[Operation],
    config: OpenAPIToolkitConfig,
) -> list[Operation]:
    """Filter list of operations based on configuration rules."""
    filtered: list[Operation] = []

    for op in operations:
        tool_name = format_tool_name(op)
        op_identifiers = {op.name, tool_name}
        if op.operation_id:
            op_identifiers.add(op.operation_id)

        if config.include_tags is not None:
            if not any(t in config.include_tags for t in op.tags):
                continue

        if config.exclude_tags is not None:
            if any(t in config.exclude_tags for t in op.tags):
                continue

        if config.include_operations is not None:
            if not any(name in config.include_operations for name in op_identifiers):
                continue

        if config.exclude_operations is not None:
            if any(name in config.exclude_operations for name in op_identifiers):
                continue

        filtered.append(op)

    return filtered


class LangChainToolFactory:
    """Factory for creating LangChain StructuredTool instances from Operations."""

    def __init__(
        self,
        executor: AsyncHTTPExecutor | None = None,
        schema_converter: SchemaConverter | None = None,
        config: OpenAPIToolkitConfig | None = None,
    ) -> None:
        self.executor = executor or AsyncHTTPExecutor()
        self.schema_converter = schema_converter or SchemaConverter()
        self.config = config or OpenAPIToolkitConfig()

    def create_tool(
        self,
        operation: Operation,
        name_override: str | None = None,
    ) -> StructuredTool:
        tool_name = name_override or format_tool_name(operation)
        description_text = build_tool_description(
            operation, tool_name=tool_name, config=self.config
        )
        args_schema = self.schema_converter.to_pydantic(operation)
        executor = self.executor

        async def _arun(**kwargs: Any) -> Any:
            try:
                result = await executor.execute(operation, kwargs)
                if result.status_code >= 400:
                    raise ToolException(
                        f"HTTP request failed with status code "
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
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(lambda: asyncio.run(_arun(**kwargs)))
                    return future.result()
            else:
                return asyncio.run(_arun(**kwargs))

        metadata: dict[str, Any] = {
            "method": operation.method.value.upper(),
            "path": operation.path,
            "operation_id": operation.operation_id,
            "tags": operation.tags,
        }

        logger.debug(
            "Created StructuredTool '%s' for %s %s",
            tool_name,
            operation.method.value.upper(),
            operation.path,
        )

        return StructuredTool.from_function(
            func=_run,
            coroutine=_arun,
            name=tool_name,
            description=description_text,
            args_schema=args_schema,
            metadata=metadata,
            handle_tool_error=True,
        )


class OpenAPIToolkit:
    """Toolkit for managing LangChain tools generated from OpenAPI specs."""

    def __init__(
        self,
        spec: OpenAPISpec,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: OpenAPIToolkitConfig | None = None,
        # Direct kwargs for backward compatibility:
        description_mode: Literal["full", "compact", "minimal"] = "full",
        compress_descriptions: bool = False,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        include_operations: list[str] | None = None,
        exclude_operations: list[str] | None = None,
        tool_description_overrides: dict[str, str] | None = None,
        description_builder: Callable[[Operation], str] | None = None,
    ) -> None:
        if config is None:
            config = OpenAPIToolkitConfig(
                description_mode=description_mode,
                compress_descriptions=compress_descriptions,
                include_tags=include_tags,
                exclude_tags=exclude_tags,
                include_operations=include_operations,
                exclude_operations=exclude_operations,
                tool_description_overrides=tool_description_overrides,
                description_builder=description_builder,
            )
        self.config = config
        self.spec = spec

        effective_base_url = base_url
        if not effective_base_url and spec.servers:
            effective_base_url = spec.servers[0]

        self.executor = AsyncHTTPExecutor(
            base_url=effective_base_url,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
        )
        self.factory = LangChainToolFactory(
            executor=self.executor,
            config=self.config,
        )

        parser = OpenAPIParser(spec)
        raw_operations = parser.parse()
        operations = filter_operations(raw_operations, self.config)

        self._tools_dict: dict[str, BaseTool] = {}
        used_names: set[str] = set()

        for op in operations:
            base_name = format_tool_name(op)
            candidate_name = base_name
            counter = 2
            while candidate_name in used_names:
                candidate_name = f"{base_name}_{counter}"
                counter += 1

            used_names.add(candidate_name)
            tool = self.factory.create_tool(op, name_override=candidate_name)
            self._tools_dict[candidate_name] = tool

        logger.info("OpenAPIToolkit initialized with %d tools.", len(self._tools_dict))

    @classmethod
    def from_url(
        cls,
        url: str,
        headers: dict[str, str] | None = None,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: OpenAPIToolkitConfig | None = None,
        **kwargs: Any,
    ) -> "OpenAPIToolkit":
        loader = OpenAPILoader.from_url(url, headers=headers)
        spec = loader.load()
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
            **kwargs,
        )

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: OpenAPIToolkitConfig | None = None,
        **kwargs: Any,
    ) -> "OpenAPIToolkit":
        loader = OpenAPILoader.from_file(file_path)
        spec = loader.load()
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
            **kwargs,
        )

    @classmethod
    def from_dict(
        cls,
        spec_dict: dict[str, Any],
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: OpenAPIToolkitConfig | None = None,
        **kwargs: Any,
    ) -> "OpenAPIToolkit":
        loader = OpenAPILoader.from_dict(spec_dict)
        spec = loader.load()
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
            **kwargs,
        )

    @classmethod
    def from_spec(
        cls,
        spec: OpenAPISpec,
        provider: RequestProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        config: OpenAPIToolkitConfig | None = None,
        **kwargs: Any,
    ) -> "OpenAPIToolkit":
        return cls(
            spec=spec,
            provider=provider,
            middleware=middleware,
            timeout=timeout,
            base_url=base_url,
            config=config,
            **kwargs,
        )

    def list_tools(self) -> list[str]:
        return list(self._tools_dict.keys())

    def get_tool(self, name: str) -> BaseTool:
        if name not in self._tools_dict:
            available = self.list_tools()
            raise KeyError(
                f"Tool '{name}' not found in toolkit. Available tools: {available}"
            )
        return self._tools_dict[name]

    def get_tools(
        self,
        methods: list[str] | None = None,
        tags: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        mode: Literal["typed", "generic", "hybrid"] = "typed",
        typed_tags: list[str] | None = None,
        typed_operations: list[str] | None = None,
    ) -> list[BaseTool]:
        """Return the typed tools, or delegate to the generic/hybrid strategy.

        The default (``mode="typed"``) keeps backward compatibility: one
        LangChain tool per operation, filtered by ``methods`` / ``tags`` /
        ``include`` / ``exclude``. Passing ``mode="generic"`` or
        ``mode="hybrid"`` transparently delegates to
        :class:`~langchain_openapi_tools.generic_toolkit.GenericOpenAPIToolkit`
        so users can opt in without switching classes.
        """
        if mode != "typed":
            # Lazy import to avoid a hard circular dependency.
            from langchain_openapi_tools.generic_toolkit import (
                GenericOpenAPIToolkit,
                GenericToolkitConfig,
            )

            generic_config = GenericToolkitConfig(
                typed_tags=typed_tags,
                typed_operations=typed_operations,
                typed_config=self.config,
            )
            generic = GenericOpenAPIToolkit(
                spec=self.spec,
                provider=self.executor.provider,
                middleware=self.executor.pipeline.middlewares,
                timeout=self.executor.timeout,
                base_url=self.executor.base_url,
                config=generic_config,
            )
            return generic.get_tools(
                mode=mode,
                typed_tags=typed_tags,
                typed_operations=typed_operations,
            )

        result: list[BaseTool] = []
        target_methods = [m.upper() for m in methods] if methods else None
        inc_set = set(include) if include else None
        exc_set = set(exclude) if exclude else None

        for tool_name, tool in self._tools_dict.items():
            meta = tool.metadata or {}
            op_id = meta.get("operation_id")
            method = meta.get("method")
            op_tags = meta.get("tags") or []

            if exc_set and (tool_name in exc_set or (op_id and op_id in exc_set)):
                continue

            if inc_set and not (tool_name in inc_set or (op_id and op_id in inc_set)):
                continue

            if target_methods and method not in target_methods:
                continue

            if tags and not any(t in op_tags for t in tags):
                continue

            result.append(tool)

        return result
