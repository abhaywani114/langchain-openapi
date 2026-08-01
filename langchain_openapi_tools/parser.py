"""OpenAPI Specification Parser and Reference Resolver."""

import logging
import re
from typing import Any

from langchain_openapi_tools.enums import DataType, HTTPMethod, ParameterLocation
from langchain_openapi_tools.exceptions import InvalidSpecError
from langchain_openapi_tools.models import (
    MediaType,
    Operation,
    Parameter,
    RequestBody,
    Response,
    Schema,
)

logger = logging.getLogger(__name__)


class OpenAPISpec:
    """Normalized internal representation of an OpenAPI specification."""

    def __init__(
        self,
        raw: dict[str, Any],
        version: str,
        title: str,
        description: str | None,
        servers: list[str],
        paths: dict[str, Any],
    ) -> None:
        self.raw = raw
        self.version = version
        self.title = title
        self.description = description
        self.servers = servers
        self.paths = paths

    @classmethod
    def from_dict(cls, spec_dict: dict[str, Any]) -> "OpenAPISpec":
        """Construct an OpenAPISpec instance from a raw dictionary."""
        swagger_ver = str(spec_dict.get("swagger", ""))
        if spec_dict.get("swagger") == "2.0" or swagger_ver.startswith("2."):
            from langchain_openapi_tools.swagger import SwaggerNormalizer

            spec_dict = SwaggerNormalizer(spec_dict).normalize()

        version = str(spec_dict.get("openapi", "3.0.0"))
        info = spec_dict.get("info")
        if not isinstance(info, dict):
            info = {}

        title = str(info.get("title", "Untitled API"))
        description = info.get("description")
        if description is not None:
            description = str(description)

        raw_servers = spec_dict.get("servers", [])
        servers: list[str] = []
        if isinstance(raw_servers, list):
            for server in raw_servers:
                if (
                    isinstance(server, dict)
                    and "url" in server
                    and isinstance(server["url"], str)
                ):
                    servers.append(server["url"])

        paths = spec_dict.get("paths", {})
        if not isinstance(paths, dict):
            paths = {}

        return cls(
            raw=spec_dict,
            version=version,
            title=title,
            description=description,
            servers=servers,
            paths=paths,
        )

    def __repr__(self) -> str:
        return f"<OpenAPISpec title={self.title!r} version={self.version!r}>"


class ReferenceResolver:
    """Recursively resolves local JSON pointers (e.g. #/components/schemas/Pet)."""

    def __init__(self, raw_spec: dict[str, Any]) -> None:
        self._raw_spec = raw_spec

    def resolve(self, data: Any, seen: set[str] | None = None) -> Any:
        """Recursively resolve $ref pointers within a data structure."""
        if seen is None:
            seen = set()

        if isinstance(data, dict):
            if "$ref" in data and isinstance(data["$ref"], str):
                ref_path = data["$ref"]
                if not ref_path.startswith("#/"):
                    raise InvalidSpecError(
                        f"Unsupported reference format '{ref_path}'. "
                        "Only local references starting with '#/' are supported."
                    )

                if ref_path in seen:
                    logger.warning(
                        "Circular reference detected for pointer '%s'", ref_path
                    )
                    shallow_copy = {k: v for k, v in data.items() if k != "$ref"}
                    return self.resolve(shallow_copy, seen=seen)

                seen_next = set(seen)
                seen_next.add(ref_path)

                resolved_target = self._lookup_pointer(ref_path)
                sibling_keys = {k: v for k, v in data.items() if k != "$ref"}

                if isinstance(resolved_target, dict):
                    merged = dict(resolved_target)
                    merged.update(sibling_keys)
                    return self.resolve(merged, seen=seen_next)

                return self.resolve(resolved_target, seen=seen_next)

            return {k: self.resolve(v, seen=seen) for k, v in data.items()}

        if isinstance(data, list):
            return [self.resolve(item, seen=seen) for item in data]

        return data

    def _lookup_pointer(self, ref_path: str) -> Any:
        parts = [
            p.replace("~1", "/").replace("~0", "~") for p in ref_path[2:].split("/")
        ]
        curr: Any = self._raw_spec

        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            elif isinstance(curr, list) and part.isdigit() and int(part) < len(curr):
                curr = curr[int(part)]
            else:
                raise InvalidSpecError(
                    f"Failed to resolve reference '{ref_path}': key '{part}' not found."
                )

        return curr


def generate_fallback_operation_name(method: str, path: str) -> str:
    """Generate a clean snake_case fallback operation name from method and path."""
    clean_path = path.strip("/")
    if not clean_path:
        return f"{method.lower()}_root"

    parts: list[str] = []
    for segment in clean_path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            param_name = segment[1:-1]
            param_clean = re.sub(r"(?<!^)(?=[A-Z])", "_", param_name).lower()
            param_clean = re.sub(r"[^\w]", "_", param_clean)
            parts.append(f"by_{param_clean}")
        else:
            segment_clean = re.sub(r"(?<!^)(?=[A-Z])", "_", segment).lower()
            segment_clean = re.sub(r"[^\w]", "_", segment_clean)
            parts.append(segment_clean)

    raw_name = f"{method.lower()}_" + "_".join(parts)
    return re.sub(r"_+", "_", raw_name).strip("_")


class OpenAPIParser:
    """Parser for converting an OpenAPISpec into normalized internal Python models."""

    def __init__(self, spec: OpenAPISpec) -> None:
        swagger_ver = str(spec.raw.get("swagger", ""))
        if spec.raw.get("swagger") == "2.0" or swagger_ver.startswith("2."):
            from langchain_openapi_tools.swagger import SwaggerNormalizer

            normalized_raw = SwaggerNormalizer(spec.raw).normalize()
            spec = OpenAPISpec.from_dict(normalized_raw)
        self._spec = spec
        self._resolver = ReferenceResolver(spec.raw)

    def parse(self) -> list[Operation]:
        """Parse all paths and operations in the specification."""
        logger.info("Parsing OpenAPI operations for '%s'", self._spec.title)
        resolved_spec = self._resolver.resolve(self._spec.raw)
        global_security = resolved_spec.get("security", [])

        operations: list[Operation] = []
        paths: dict[str, Any] = resolved_spec.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            path_params = self._parse_parameters(path_item.get("parameters", []))

            for key, val in path_item.items():
                if key.upper() not in HTTPMethod.__members__:
                    continue

                if not isinstance(val, dict):
                    continue

                method = HTTPMethod(key.upper())
                operation = self._parse_operation(
                    method=method,
                    path=path,
                    op_dict=val,
                    path_params=path_params,
                    global_security=global_security,
                )
                operations.append(operation)

        logger.info("Parsed %d operations from '%s'", len(operations), self._spec.title)
        return operations

    def _parse_operation(
        self,
        method: HTTPMethod,
        path: str,
        op_dict: dict[str, Any],
        path_params: list[Parameter],
        global_security: list[dict[str, list[str]]],
    ) -> Operation:
        explicit_id = op_dict.get("operationId")
        if explicit_id and isinstance(explicit_id, str):
            op_id: str | None = explicit_id
            name = explicit_id
        else:
            op_id = None
            name = generate_fallback_operation_name(method.value, path)

        summary = op_dict.get("summary")
        description = op_dict.get("description")
        deprecated = bool(op_dict.get("deprecated", False))
        tags = [str(t) for t in op_dict.get("tags", []) if isinstance(t, str)]

        op_param_list = self._parse_parameters(op_dict.get("parameters", []))
        param_map: dict[tuple[str, str], Parameter] = {}
        for p in path_params:
            param_map[(p.name, p.location.value)] = p
        for p in op_param_list:
            param_map[(p.name, p.location.value)] = p

        parameters = list(param_map.values())
        request_body = self._parse_request_body(op_dict.get("requestBody"))
        responses = self._parse_responses(op_dict.get("responses"))

        security = op_dict.get("security", global_security)

        return Operation(
            name=name,
            method=method,
            path=path,
            summary=str(summary) if summary is not None else None,
            description=str(description) if description is not None else None,
            operation_id=op_id,
            tags=tags,
            parameters=parameters,
            request_body=request_body,
            responses=responses,
            deprecated=deprecated,
            security=security if isinstance(security, list) else [],
        )

    def _parse_parameters(self, raw_params: list[Any]) -> list[Parameter]:
        params: list[Parameter] = []
        if not isinstance(raw_params, list):
            return params

        for item in raw_params:
            if not isinstance(item, dict):
                continue

            name = item.get("name")
            location_str = item.get("in")
            if not name or not location_str or not isinstance(name, str):
                continue

            try:
                location = ParameterLocation(location_str)
            except ValueError:
                logger.warning(
                    "Skipping parameter '%s' with unknown location '%s'",
                    name,
                    location_str,
                )
                continue

            is_path = location == ParameterLocation.PATH
            required = bool(item.get("required", True if is_path else False))
            description = item.get("description")
            schema_dict = item.get("schema")
            schema = self._parse_schema(schema_dict) if schema_dict else None

            default = item.get("default")
            if default is None and schema and schema.default is not None:
                default = schema.default

            params.append(
                Parameter(
                    name=name,
                    location=location,
                    required=required,
                    description=str(description) if description is not None else None,
                    schema=schema,
                    default=default,
                    example=item.get("example"),
                    style=str(item["style"]) if item.get("style") is not None else None,
                    explode=bool(item["explode"])
                    if item.get("explode") is not None
                    else None,
                )
            )

        return params

    def _parse_request_body(
        self, raw_body: dict[str, Any] | None
    ) -> RequestBody | None:
        if not isinstance(raw_body, dict):
            return None

        content_dict = raw_body.get("content", {})
        content: dict[str, MediaType] = {}

        if isinstance(content_dict, dict):
            for content_type, media_raw in content_dict.items():
                if isinstance(media_raw, dict):
                    content[str(content_type)] = self._parse_media_type(
                        str(content_type), media_raw
                    )

        desc = raw_body.get("description")
        return RequestBody(
            required=bool(raw_body.get("required", False)),
            description=str(desc) if desc is not None else None,
            content=content,
        )

    def _parse_responses(
        self, raw_responses: dict[str, Any] | None
    ) -> dict[str, Response]:
        responses: dict[str, Response] = {}
        if not isinstance(raw_responses, dict):
            return responses

        for status_code, resp_raw in raw_responses.items():
            if not isinstance(resp_raw, dict):
                continue

            content_dict = resp_raw.get("content", {})
            content: dict[str, MediaType] = {}

            if isinstance(content_dict, dict):
                for content_type, media_raw in content_dict.items():
                    if isinstance(media_raw, dict):
                        content[str(content_type)] = self._parse_media_type(
                            str(content_type), media_raw
                        )

            responses[str(status_code)] = Response(
                status_code=str(status_code),
                description=str(resp_raw.get("description", "")),
                content=content,
            )

        return responses

    def _parse_media_type(
        self, content_type: str, raw_media: dict[str, Any]
    ) -> MediaType:
        schema_dict = raw_media.get("schema")
        schema = (
            self._parse_schema(schema_dict) if isinstance(schema_dict, dict) else None
        )

        return MediaType(
            content_type=content_type,
            schema=schema,
            example=raw_media.get("example"),
            examples=raw_media.get("examples")
            if isinstance(raw_media.get("examples"), dict)
            else None,
        )

    def _parse_schema(self, raw_schema: dict[str, Any] | None) -> Schema | None:
        if not isinstance(raw_schema, dict):
            return None

        raw_type = raw_schema.get("type")
        nullable = bool(raw_schema.get("nullable", False))
        type_val: DataType | str | list[DataType | str] | None = None

        if isinstance(raw_type, str):
            try:
                type_val = DataType(raw_type)
            except ValueError:
                type_val = raw_type
        elif isinstance(raw_type, list):
            parsed_types: list[DataType | str] = []
            for t in raw_type:
                if t == "null":
                    nullable = True
                elif isinstance(t, str):
                    try:
                        parsed_types.append(DataType(t))
                    except ValueError:
                        parsed_types.append(t)
            type_val = parsed_types

        props_dict = raw_schema.get("properties")
        properties: dict[str, Schema] | None = None
        if isinstance(props_dict, dict):
            properties = {}
            for p_name, p_schema in props_dict.items():
                if isinstance(p_schema, dict):
                    parsed_p = self._parse_schema(p_schema)
                    if parsed_p:
                        properties[str(p_name)] = parsed_p

        items_dict = raw_schema.get("items")
        items = self._parse_schema(items_dict) if isinstance(items_dict, dict) else None

        format_val = raw_schema.get("format")
        desc = raw_schema.get("description")
        enum_val = raw_schema.get("enum")
        req_list = raw_schema.get("required")

        return Schema(
            type=type_val,
            format=str(format_val) if format_val is not None else None,
            properties=properties,
            items=items,
            required=[str(r) for r in req_list] if isinstance(req_list, list) else None,
            enum=list(enum_val) if isinstance(enum_val, list) else None,
            default=raw_schema.get("default"),
            nullable=nullable,
            description=str(desc) if desc is not None else None,
        )
