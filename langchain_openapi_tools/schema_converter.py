"""OpenAPI Schema to Dynamic Pydantic Model Converter."""

import logging
import re
from enum import Enum
from functools import reduce
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

from langchain_openapi_tools.enums import DataType
from langchain_openapi_tools.models import Operation, Schema

logger = logging.getLogger(__name__)

OPENAPI_TYPE_TO_PYTHON: dict[DataType | str, type] = {
    DataType.STRING: str,
    "string": str,
    DataType.INTEGER: int,
    "integer": int,
    DataType.NUMBER: float,
    "number": float,
    DataType.BOOLEAN: bool,
    "boolean": bool,
    DataType.ARRAY: list,
    "array": list,
    DataType.OBJECT: dict,
    "object": dict,
}


def map_schema_type_to_python(
    type_val: DataType | str | list[DataType | str] | None,
) -> type:
    """Map OpenAPI schema type specification to standard Python types."""
    if type_val is None:
        return Any

    if isinstance(type_val, list):
        non_null_types = [t for t in type_val if t != "null"]
        if non_null_types:
            return map_schema_type_to_python(non_null_types[0])
        return Any

    return OPENAPI_TYPE_TO_PYTHON.get(type_val, Any)


def _union_of(types: list[Any]) -> Any:
    """Return a Union[...] annotation collapsing duplicates and empty lists."""
    unique: list[Any] = []
    for t in types:
        if t is None:
            continue
        if t not in unique:
            unique.append(t)
    if not unique:
        return Any
    if len(unique) == 1:
        return unique[0]
    return reduce(lambda a, b: Union[a, b], unique)  # noqa: UP007


def _merge_all_of(schemas: list[Schema]) -> Schema:
    """Shallow-merge a list of subschemas into a single composite Schema.

    Used to flatten ``allOf`` for the purposes of Pydantic model synthesis.
    Properties from later subschemas override earlier ones; ``required``
    lists are unioned.
    """
    merged = Schema()
    merged_props: dict[str, Schema] = {}
    merged_required: list[str] = []

    for sub in schemas:
        if sub.type and merged.type is None:
            merged.type = sub.type
        if sub.format and merged.format is None:
            merged.format = sub.format
        if sub.properties:
            merged_props.update(sub.properties)
        if sub.required:
            for r in sub.required:
                if r not in merged_required:
                    merged_required.append(r)
        if sub.description and merged.description is None:
            merged.description = sub.description
        if sub.default is not None and merged.default is None:
            merged.default = sub.default
        if sub.enum and merged.enum is None:
            merged.enum = list(sub.enum)
        if sub.items and merged.items is None:
            merged.items = sub.items
        merged.nullable = merged.nullable or sub.nullable
        merged.read_only = merged.read_only or sub.read_only
        merged.write_only = merged.write_only or sub.write_only
        merged.deprecated = merged.deprecated or sub.deprecated

    if merged_props:
        merged.properties = merged_props
        if merged.type is None:
            merged.type = DataType.OBJECT
    if merged_required:
        merged.required = merged_required
    return merged


def to_camel_case(snake_str: str) -> str:
    """Convert snake_case or identifier string to CamelCase."""
    clean_str = re.sub(r"[^\w]", "_", snake_str)
    if "_" in clean_str:
        components = clean_str.split("_")
        return "".join(x[:1].upper() + x[1:] for x in components if x)
    return clean_str[:1].upper() + clean_str[1:]


def create_dynamic_enum(enum_name: str, values: list[Any]) -> type[Enum]:
    """Create a dynamic Python string Enum for OpenAPI enum values."""
    members = {}
    for v in values:
        s_val = str(v)
        member_name = re.sub(r"[^\w]", "_", s_val)
        if member_name and member_name[0].isdigit():
            member_name = f"VALUE_{member_name}"
        if not member_name:
            member_name = "EMPTY"
        members[member_name] = s_val

    return Enum(enum_name, members, type=str)  # type: ignore[return-value]


class PydanticFactory:
    """Factory for dynamically creating Pydantic models from internal Schema objects."""

    def __init__(self) -> None:
        self._generated_enums: dict[str, type[Enum]] = {}
        self._generated_models: dict[str, type[BaseModel]] = {}

    def schema_to_annotation_and_field(
        self,
        schema: Schema | None,
        parent_name: str,
        field_name: str,
        is_required: bool,
        description: str | None = None,
        default_override: Any = None,
    ) -> tuple[Any, Any]:
        """Convert a Schema instance into a (type_annotation, Field) pair."""
        desc = description or (schema.description if schema else None)
        default_val = (
            default_override
            if default_override is not None
            else (schema.default if schema else None)
        )

        py_type = self._build_type_annotation(
            schema=schema,
            parent_name=parent_name,
            field_name=field_name,
        )

        nullable = bool(schema and schema.nullable)

        if default_val is not None:
            field_info = Field(default=default_val, description=desc)
            annotation = py_type | None if nullable else py_type
        elif is_required:
            field_info = Field(..., description=desc)
            annotation = py_type | None if nullable else py_type
        else:
            field_info = Field(default=None, description=desc)
            annotation = py_type | None

        return annotation, field_info

    def _build_type_annotation(
        self,
        schema: Schema | None,
        parent_name: str,
        field_name: str,
    ) -> Any:
        if schema is None:
            return str

        # ``allOf`` — merge subschemas and synthesize a single Pydantic model.
        if schema.all_of:
            merged = _merge_all_of(schema.all_of)
            if schema.properties:
                merged = _merge_all_of([merged, schema])
            return self._build_type_annotation(
                schema=merged,
                parent_name=parent_name,
                field_name=field_name,
            )

        # ``oneOf`` / ``anyOf`` — emit a Union of subschema annotations.
        variants = list(schema.one_of or []) + list(schema.any_of or [])
        if variants:
            variant_types: list[Any] = []
            for i, sub in enumerate(variants):
                variant_types.append(
                    self._build_type_annotation(
                        schema=sub,
                        parent_name=parent_name,
                        field_name=f"{field_name}_variant_{i}",
                    )
                )
            union_ann = _union_of(variant_types)
            return union_ann | None if schema.nullable else union_ann

        if schema.enum:
            enum_class_name = f"{parent_name}_{to_camel_case(field_name)}Enum"
            if enum_class_name not in self._generated_enums:
                self._generated_enums[enum_class_name] = create_dynamic_enum(
                    enum_class_name, schema.enum
                )
            return self._generated_enums[enum_class_name]

        if schema.properties is not None or schema.type == DataType.OBJECT:
            nested_model_name = f"{parent_name}_{to_camel_case(field_name)}"
            if nested_model_name in self._generated_models:
                return self._generated_models[nested_model_name]

            nested_fields: dict[str, tuple[Any, Any]] = {}
            props = schema.properties or {}
            req_set = set(schema.required or [])

            for prop_name, prop_schema in props.items():
                is_prop_req = prop_name in req_set
                ann, finfo = self.schema_to_annotation_and_field(
                    schema=prop_schema,
                    parent_name=nested_model_name,
                    field_name=prop_name,
                    is_required=is_prop_req,
                )
                nested_fields[prop_name] = (ann, finfo)

            nested_model = create_model(nested_model_name, **nested_fields)  # type: ignore[call-overload]
            self._generated_models[nested_model_name] = nested_model
            return nested_model

        if schema.type == DataType.ARRAY or schema.type == "array":
            if schema.items:
                item_type = self._build_type_annotation(
                    schema=schema.items,
                    parent_name=f"{parent_name}_{to_camel_case(field_name)}Item",
                    field_name="item",
                )
                return list[item_type]  # type: ignore[valid-type]
            return list[Any]

        # OpenAPI 3.1 union types (``type: [X, Y]``) — emit Union[X, Y].
        if isinstance(schema.type, list):
            union_types = [
                map_schema_type_to_python(t)
                for t in schema.type
                if t != "null"
            ]
            return _union_of(union_types)

        return map_schema_type_to_python(schema.type)


class SchemaConverter:
    """Converter that turns internal Operation models into dynamic Pydantic models."""

    def __init__(self) -> None:
        self._factory = PydanticFactory()

    def to_pydantic(self, operation: Operation) -> type[BaseModel]:
        """Convert an Operation into a dynamic Pydantic input model class."""
        raw_name = to_camel_case(operation.name)
        model_name = f"{raw_name}Input" if not raw_name.endswith("Input") else raw_name

        field_definitions: dict[str, tuple[Any, Any]] = {
            "paginate": (
                bool | None,
                Field(
                    default=None,
                    description=(
                        "Optional. Set to True to aggregate multi-page responses."
                    ),
                ),
            ),
        }

        for param in operation.parameters:
            ann, finfo = self._factory.schema_to_annotation_and_field(
                schema=param.schema,
                parent_name=model_name,
                field_name=param.name,
                is_required=param.required,
                description=param.description,
                default_override=param.default,
            )
            field_definitions[param.name] = (ann, finfo)

        if operation.request_body and operation.request_body.content:
            content_dict = operation.request_body.content
            media_type = content_dict.get(
                "application/json", next(iter(content_dict.values()))
            )

            body_schema = media_type.schema
            if body_schema:
                # Flatten top-level ``allOf`` so downstream field-splitting
                # sees the merged property set.
                if body_schema.all_of and not body_schema.properties:
                    body_schema = _merge_all_of(body_schema.all_of)

                body_req = operation.request_body.required
                body_desc = operation.request_body.description

                if (
                    body_schema.type == DataType.OBJECT or body_schema.properties
                ) and body_schema.properties:
                    req_set = set(body_schema.required or [])
                    for p_name, p_schema in body_schema.properties.items():
                        if p_name in field_definitions:
                            ann, finfo = self._factory.schema_to_annotation_and_field(
                                schema=body_schema,
                                parent_name=model_name,
                                field_name="body",
                                is_required=body_req,
                                description=body_desc,
                            )
                            field_definitions["body"] = (ann, finfo)
                            break

                        is_p_req = body_req and (p_name in req_set)
                        ann, finfo = self._factory.schema_to_annotation_and_field(
                            schema=p_schema,
                            parent_name=model_name,
                            field_name=p_name,
                            is_required=is_p_req,
                        )
                        field_definitions[p_name] = (ann, finfo)
                else:
                    ann, finfo = self._factory.schema_to_annotation_and_field(
                        schema=body_schema,
                        parent_name=model_name,
                        field_name="body",
                        is_required=body_req,
                        description=body_desc,
                    )
                    field_definitions["body"] = (ann, finfo)

        logger.debug("Created Pydantic model '%s'", model_name)
        model: type[BaseModel] = create_model(
            model_name,
            __config__=ConfigDict(extra="allow"),
            **field_definitions,
        )  # type: ignore[call-overload]
        return model
