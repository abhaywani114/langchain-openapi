"""Swagger 2.0 to OpenAPI 3.0 specification normalizer."""

import copy
from typing import Any
from urllib.parse import urlparse


class SwaggerNormalizer:
    """Normalizes raw Swagger 2.0 specification dictionary into OpenAPI 3.0 format."""

    def __init__(
        self,
        raw_spec: dict[str, Any],
        source_url: str | None = None,
    ) -> None:
        """Initialize the normalizer.

        Args:
            raw_spec: Raw Swagger 2.0 specification dictionary.
            source_url: Optional URL the specification was fetched from. Used
                to fill in ``host`` / ``schemes`` when the spec omits them,
                which is common for APIs that self-describe (e.g. Azure /
                ASP.NET Swashbuckle endpoints).
        """
        self.raw = copy.deepcopy(raw_spec)
        self.source_url = source_url

    def normalize(self) -> dict[str, Any]:
        """Convert Swagger 2.0 spec dictionary into an OpenAPI 3.0 compliant dictionary.

        Returns:
            Normalized OpenAPI 3.0 specification dictionary.
        """
        spec = self.raw
        version = str(spec.get("swagger", ""))
        if not (spec.get("swagger") == "2.0" or version.startswith("2.")):
            return spec

        normalized: dict[str, Any] = {
            "openapi": "3.0.3",
            "info": spec.get("info", {}),
        }

        if "tags" in spec:
            normalized["tags"] = spec["tags"]

        # 1. Servers
        servers = self._convert_servers(spec)
        if servers:
            normalized["servers"] = servers

        # 2. Components
        components = self._convert_components(spec)
        if components:
            normalized["components"] = components

        # 3. Security Requirements
        if "security" in spec:
            normalized["security"] = spec["security"]

        # 4. Paths
        global_consumes = spec.get("consumes", ["application/json"])
        global_produces = spec.get("produces", ["application/json"])
        paths = spec.get("paths", {})
        normalized["paths"] = self._convert_paths(
            paths, global_consumes, global_produces
        )

        # 5. Reference Rewriting ($ref)
        normalized = self._rewrite_references(normalized)

        return normalized

    def _convert_servers(self, spec: dict[str, Any]) -> list[dict[str, str]]:
        host = str(spec.get("host", "")).strip()
        base_path = str(spec.get("basePath", "")).strip()
        schemes = spec.get("schemes", [])

        # Swagger 2.0: if host is missing, the API is served from the same host
        # as the specification itself. Fall back to the document location so
        # RequestBuilder can construct absolute URLs.
        source_parsed = urlparse(self.source_url) if self.source_url else None

        if not host and source_parsed and source_parsed.netloc:
            host = source_parsed.netloc
            if (not isinstance(schemes, list) or not schemes) and source_parsed.scheme:
                schemes = [source_parsed.scheme]

        if host:
            if "://" in host:
                scheme_part, host_part = host.split("://", 1)
                schemes = [scheme_part]
                host = host_part

            if not isinstance(schemes, list) or not schemes:
                schemes = ["https"]

            if base_path == "/":
                base_path = ""
            elif base_path and not base_path.startswith("/"):
                base_path = f"/{base_path}"

            servers: list[dict[str, str]] = []
            for scheme in schemes:
                url = f"{scheme}://{host}{base_path}".rstrip("/")
                servers.append({"url": url})
            return servers
        elif base_path:
            base_path_clean = base_path.rstrip("/")
            if base_path_clean:
                return [{"url": base_path_clean}]
        return []

    def _convert_components(self, spec: dict[str, Any]) -> dict[str, Any]:
        components: dict[str, Any] = {}

        if "definitions" in spec and isinstance(spec["definitions"], dict):
            components["schemas"] = spec["definitions"]

        if "parameters" in spec and isinstance(spec["parameters"], dict):
            converted_params: dict[str, Any] = {}
            for param_name, param_obj in spec["parameters"].items():
                if isinstance(param_obj, dict):
                    converted_params[param_name] = self._convert_parameter(param_obj)
            components["parameters"] = converted_params

        if "responses" in spec and isinstance(spec["responses"], dict):
            converted_responses: dict[str, Any] = {}
            global_produces = spec.get("produces", ["application/json"])
            for resp_name, resp_obj in spec["responses"].items():
                if isinstance(resp_obj, dict):
                    converted_responses[resp_name] = self._convert_response(
                        resp_obj, global_produces
                    )
            components["responses"] = converted_responses

        if "securityDefinitions" in spec and isinstance(
            spec["securityDefinitions"], dict
        ):
            components["securitySchemes"] = self._convert_security_definitions(
                spec["securityDefinitions"]
            )

        return components

    def _convert_security_definitions(self, sec_defs: dict[str, Any]) -> dict[str, Any]:
        schemes: dict[str, Any] = {}
        for name, sec in sec_defs.items():
            if not isinstance(sec, dict):
                continue
            sec_type = sec.get("type")
            if sec_type == "basic":
                schemes[name] = {"type": "http", "scheme": "basic"}
            elif sec_type == "apiKey":
                schemes[name] = {
                    "type": "apiKey",
                    "name": sec.get("name", name),
                    "in": sec.get("in", "header"),
                }
            elif sec_type == "oauth2":
                flow = sec.get("flow")
                flow_key = flow
                if flow == "accessCode":
                    flow_key = "authorizationCode"
                elif flow == "application":
                    flow_key = "clientCredentials"

                flow_obj: dict[str, Any] = {
                    "scopes": sec.get("scopes", {}),
                }
                if sec.get("authorizationUrl"):
                    flow_obj["authorizationUrl"] = sec["authorizationUrl"]
                if sec.get("tokenUrl"):
                    flow_obj["tokenUrl"] = sec["tokenUrl"]

                schemes[name] = {
                    "type": "oauth2",
                    "flows": {flow_key: flow_obj} if flow_key else {},
                }
            else:
                schemes[name] = sec
            if "description" in sec:
                schemes[name]["description"] = sec["description"]
        return schemes

    def _convert_paths(
        self,
        paths: dict[str, Any],
        global_consumes: list[str],
        global_produces: list[str],
    ) -> dict[str, Any]:
        converted_paths: dict[str, Any] = {}

        for path_str, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            new_path_item: dict[str, Any] = {}
            path_parameters = path_item.get("parameters", [])

            for key, val in path_item.items():
                if key in (
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                    "trace",
                ):
                    if isinstance(val, dict):
                        new_path_item[key] = self._convert_operation(
                            val, global_consumes, global_produces, path_parameters
                        )
                elif key != "parameters":
                    new_path_item[key] = val

            converted_paths[path_str] = new_path_item

        return converted_paths

    def _convert_operation(
        self,
        operation: dict[str, Any],
        global_consumes: list[str],
        global_produces: list[str],
        path_parameters: list[Any],
    ) -> dict[str, Any]:
        op = copy.deepcopy(operation)
        op_consumes = op.pop("consumes", global_consumes)
        op_produces = op.pop("produces", global_produces)

        # Merge path parameters and operation parameters
        all_params = list(path_parameters) + op.get("parameters", [])
        normal_params: list[dict[str, Any]] = []
        body_param: dict[str, Any] | None = None
        form_params: list[dict[str, Any]] = []

        for p in all_params:
            if not isinstance(p, dict):
                continue
            p_in = p.get("in")
            if p_in == "body":
                body_param = p
            elif p_in == "formData":
                form_params.append(p)
            else:
                normal_params.append(self._convert_parameter(p))

        op["parameters"] = normal_params

        # Convert Request Body (from in: body or in: formData)
        if body_param:
            op["requestBody"] = self._convert_body_parameter(body_param, op_consumes)
        elif form_params:
            op["requestBody"] = self._convert_form_parameters(form_params, op_consumes)

        # Convert Responses
        if "responses" in op and isinstance(op["responses"], dict):
            converted_resps: dict[str, Any] = {}
            for code, resp in op["responses"].items():
                if isinstance(resp, dict):
                    converted_resps[str(code)] = self._convert_response(
                        resp, op_produces
                    )
            op["responses"] = converted_resps

        return op

    def _convert_parameter(self, param: dict[str, Any]) -> dict[str, Any]:
        p = copy.deepcopy(param)
        if "schema" in p:
            return p

        # Move top-level schema attributes into schema dict
        schema: dict[str, Any] = {}
        for attr in (
            "type",
            "format",
            "items",
            "enum",
            "default",
            "minimum",
            "maximum",
            "minLength",
            "maxLength",
            "pattern",
            "minItems",
            "maxItems",
            "uniqueItems",
            "multipleOf",
        ):
            if attr in p:
                schema[attr] = p.pop(attr)

        if schema:
            p["schema"] = schema
        return p

    def _convert_body_parameter(
        self, body_param: dict[str, Any], consumes: list[str]
    ) -> dict[str, Any]:
        schema = body_param.get("schema", {})
        content: dict[str, Any] = {}

        media_types = consumes if consumes else ["application/json"]
        for media_type in media_types:
            content[media_type] = {"schema": schema}

        req_body: dict[str, Any] = {"content": content}
        if "description" in body_param:
            req_body["description"] = body_param["description"]
        if "required" in body_param:
            req_body["required"] = body_param["required"]

        return req_body

    def _convert_form_parameters(
        self, form_params: list[dict[str, Any]], consumes: list[str]
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        has_file = False

        for p in form_params:
            name = p.get("name")
            if not name:
                continue
            if p.get("required"):
                required.append(name)

            p_type = p.get("type", "string")
            if p_type == "file":
                has_file = True
                prop_schema: dict[str, Any] = {"type": "string", "format": "binary"}
            else:
                prop_schema = {}
                for attr in (
                    "type",
                    "format",
                    "items",
                    "enum",
                    "default",
                    "description",
                ):
                    if attr in p:
                        prop_schema[attr] = p[attr]
            properties[name] = prop_schema

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        media_type = (
            "multipart/form-data"
            if has_file
            else (consumes[0] if consumes else "application/x-www-form-urlencoded")
        )

        return {
            "required": bool(required),
            "content": {media_type: {"schema": schema}},
        }

    def _convert_response(
        self, resp: dict[str, Any], produces: list[str]
    ) -> dict[str, Any]:
        r = copy.deepcopy(resp)
        if "schema" in r:
            schema = r.pop("schema")
            content: dict[str, Any] = {}
            media_types = produces if produces else ["application/json"]
            for media_type in media_types:
                content[media_type] = {"schema": schema}
            r["content"] = content
        return r

    def _rewrite_references(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            new_dict: dict[str, Any] = {}
            for k, v in obj.items():
                if k == "$ref" and isinstance(v, str):
                    ref_str = v
                    ref_str = ref_str.replace("#/definitions/", "#/components/schemas/")
                    ref_str = ref_str.replace(
                        "#/parameters/", "#/components/parameters/"
                    )
                    ref_str = ref_str.replace("#/responses/", "#/components/responses/")
                    ref_str = ref_str.replace(
                        "#/securityDefinitions/", "#/components/securitySchemes/"
                    )
                    new_dict[k] = ref_str
                else:
                    new_dict[k] = self._rewrite_references(v)
            return new_dict
        elif isinstance(obj, list):
            return [self._rewrite_references(item) for item in obj]
        return obj
