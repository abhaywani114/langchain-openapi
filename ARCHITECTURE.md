# `langchain-openapi` Architecture Specification

This document details the planned software architecture for `langchain-openapi`.

---

## 1. Design Goals

* **Framework Native**: Seamless integration with `langchain-core` tool interfaces (`BaseTool`), ensuring drop-in compatibility with LangChain agents and LangGraph workflows.
* **Type Safety & Reliability**: Full static typing across the pipeline, converting OpenAPI definitions into strict Pydantic schemas to validate LLM tool calls before network invocation.
* **Robust Spec Support**: Comprehensive parsing of OpenAPI v3.0 and v3.1 specifications, including complete parameter locations (path, query, header, cookie) and `$ref` schema resolution.
* **Decoupled Architecture**: Clear separation of concerns between specification parsing, internal model representation, schema generation, and network execution.
* **Security First**: Safe isolation of authentication credentials so API secrets are never exposed to LLM prompts or output logs.
* **Extensibility**: Modular interfaces allowing custom HTTP transports, custom authentication handlers, and custom tool filtering strategies.

---

## 2. High-Level Architecture

The library is structured as a linear transform pipeline with isolated responsibilities:

```text
 ┌────────────────────────────────────────────────────────┐
 │                      OpenAPI Spec                      │
 │                   (File / URL / Dict)                  │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                     OpenAPI Loader                     │
 │          - Parsing (JSON / YAML)                       │
 │          - Ref Resolution ($ref expansion)             │
 │          - Remembers spec source URL                   │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                    Spec Adapter Layer                  │
 │          - Version detection (swagger2 / 3.0 / 3.1)    │
 │          - Swagger2Adapter → OpenAPI 3.0 normalization │
 │          - OpenAPI3Adapter (pass-through, 3.0 & 3.1)   │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                    Internal Models                     │
 │          - Parsed Spec & Operation trees               │
 │          - Schema normalization (incl. oneOf/anyOf/    │
 │            allOf / const / read-write flags)           │
 │          - `spec_family` tag preserved from adapter    │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                   Schema Converter                     │
 │          - JSON Schema ──► Pydantic Model              │
 │          - Parameter & Body validation schemas         │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                     HTTP Executor                      │
 │          - Async Transport (httpx)                     │
 │          - Auth Injection                              │
 │          - Request Serialization & Response Parsing    │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                     Tool Generator                     │
 │          - langchain_core.tools.BaseTool Factory       │
 │          - Selective filtering (tags, endpoints)       │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                LangChain / Agent Loop                  │
 └────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 OpenAPI Loader

The **OpenAPI Loader** is responsible for reading OpenAPI specifications from local file paths, raw strings, or remote HTTP URLs. It handles format auto-detection (JSON vs. YAML), syntax validation, and recursively resolves relative and external `$ref` pointers into a unified, flattened schema representation.

When loading from a URL, the loader preserves the source URL on the resulting `OpenAPISpec` (`spec.source_url`). This lets `OpenAPISpec.from_dict` and `SwaggerNormalizer` resolve relative `servers` entries and missing `host` fields to absolute URLs, so `RequestBuilder` always receives an absolute base URL — even for specs like `https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json` that omit the `servers` block entirely.

### 3.2 Spec Adapter Layer

The **Spec Adapter Layer** (`langchain_openapi_tools.adapters`) provides a
uniform entry point across every supported specification family. It exposes:

* `detect_spec_version(spec_dict) -> Literal["swagger2", "openapi30", "openapi31"]`
* `SpecAdapter` (`typing.Protocol`) — the shared adapter interface.
* `Swagger2Adapter` — wraps `SwaggerNormalizer` to lift Swagger 2.0 documents
  into an OpenAPI 3.0-compatible dictionary while remembering the source URL
  so `host`/`basePath` gaps can be filled in from the fetch location.
* `OpenAPI3Adapter` — a pass-through adapter for both OpenAPI 3.0.x and
  3.1.x documents.
* `select_adapter(spec_dict)` and `normalize_spec(spec_dict, source_url)` —
  convenience helpers that pick the right adapter and return a `(normalized
  dict, spec_family)` tuple.

`OpenAPISpec.from_dict` calls `normalize_spec` before parsing so downstream
components (`OpenAPIParser`, `SchemaConverter`, `RequestBuilder`) only ever
see a single canonical shape. `OpenAPISpec.spec_family` records which
family the document originated from, which is useful for logging and for
version-aware feature toggles in the future.

### 3.3 Internal Models & Specification Parser

The **OpenAPI Parser** (`OpenAPIParser`) transforms an `OpenAPISpec` into strongly typed, normalized Python dataclasses using the `ReferenceResolver` for local `$ref` pointer resolution:

```text
OpenAPI Spec (File / URL / Dict)
               │
               ▼
       [ OpenAPISpec ]
               │
               ▼
      [ OpenAPIParser ] ◄── [ ReferenceResolver ($ref resolution) ]
               │
               ▼
     [ Operation Models ]
```

#### Public Model Definitions

* **`Operation`**: Represents a single executable API endpoint for a specific HTTP method (`name`, `method`, `path`, `summary`, `description`, `operation_id`, `tags`, `parameters`, `request_body`, `responses`, `deprecated`, `security`).
* **`Parameter`**: Defines an input parameter supplied in a request (`name`, `location` [`path`, `query`, `header`, `cookie`], `required`, `description`, `schema`, `default`, `example`, `style`, `explode`).
* **`RequestBody`**: Defines the payload expected by POST/PUT/PATCH operations (`required`, `description`, `content`).
* **`Response`**: Defines an HTTP response status definition (`status_code`, `description`, `content`).
* **`MediaType`**: Maps a MIME content-type string to its schema and example payloads (`content_type`, `schema`, `example`, `examples`).
* **`Schema`**: Normalized schema structure representing primitive and complex types (`type`, `format`, `properties`, `items`, `required`, `enum`, `default`, `nullable`, `description`, `const`, `one_of`, `any_of`, `all_of`, `read_only`, `write_only`, `deprecated`).

#### Current Scope Limitations

The parser handles JSON Schema union keywords (`oneOf`, `anyOf`, `allOf`) and
OpenAPI 3.1 features such as list-form `type` and `const`, but intentionally
skips:
- `discriminator`-driven union routing.
- OpenAPI callbacks, links, and webhooks.
- `patternProperties`, `$dynamicRef`, `$dynamicAnchor`.
- Advanced example inheritance chains.

### 3.4 Schema Converter

The **Schema Converter** (`SchemaConverter` and `PydanticFactory`) converts internal schema models (`Schema`) into dynamic Pydantic `BaseModel` classes using `pydantic.create_model()`.

```text
OpenAPI Schema

       │
       ▼
Internal Schema Model

       │
       ▼
Dynamic Pydantic Model (type[BaseModel])
```

#### OpenAPI to Python / Pydantic Mapping Table

| OpenAPI Type | Python / Pydantic Target Type | Notes / Examples |
|---|---|---|
| `string` | `str` | Includes optional field descriptions |
| `integer` | `int` | Maps default values |
| `number` | `float` | Supports floats |
| `boolean` | `bool` | True / False |
| `array` | `list[T]` | Recursively typed items (e.g. `list[str]`) |
| `object` | Dynamic `BaseModel` | Dynamic nested models (e.g. `SearchWorksInput_Address`) |
| `enum` | Dynamic `Enum` | String Enum subclass (e.g. `SortEnum`) |
| `oneOf` / `anyOf` | `typing.Union[...]` | Variants are recursively converted |
| `allOf` | Merged `BaseModel` | Properties and `required` sets are combined |
| `type: [X, "null"]` | `Optional[X]` | 3.1-style nullable union |
| `nullable: true` | `Optional[X]` | 3.0-style nullable flag |
| `const` | `Literal[value]` | Fixed constant value |

#### Model Naming Conventions

* **Operation Models**: `{CamelCaseOperationName}Input` (e.g., `SearchWorksInput`).
* **Nested Object Models**: `{ParentModel}_{CamelCaseFieldName}` (e.g., `SearchWorksInput_Address`).
* **Dynamic Enums**: `{ParentModel}_{CamelCaseFieldName}Enum` (e.g., `SearchWorksInput_SortEnum`).

#### Current Limitations

The converter now covers `oneOf` / `anyOf` / `allOf`, list-form `type`,
`nullable`, and `const`. It intentionally does not yet cover:
- `discriminator`-driven union routing (variants are unions without tag dispatch).
- Recursive schemas.
- XML schema-driven request serialization.
- `patternProperties`, `$dynamicRef`, `$dynamicAnchor`.

### 3.5 Async HTTP Executor Engine

The **Async HTTP Executor** (`AsyncHTTPExecutor`) executes an `Operation` asynchronously using `httpx.AsyncClient`, transforming inputs into normalized `ResponseData` instances.

```text
Operation + Validated Arguments
               │
               ▼
       [ RequestBuilder ]
               │
               ▼
        [ AuthProvider ]
               │
               ▼
     [ AsyncHTTPExecutor ] ──► ( httpx.AsyncClient )
               │
               ▼
       [ ResponseParser ]
               │
               ▼
          ResponseData
```

#### Key Architecture Components

* **`RequestBuilder`**: Translates path, query, header, cookie, and JSON body parameters into a `BuiltRequest` object.
* **`AuthProvider`**: Abstract interface (`NoAuth`, `BearerAuth`, `APIKeyHeaderAuth`, `APIKeyQueryAuth`, `BasicAuth`) for injecting security credentials.
* **`ResponseParser`**: Normalizes HTTP response payloads into `ResponseData` (`status_code`, `headers`, `body`, `raw`), attempting JSON decoding with graceful plain text fallback.

#### Exception Hierarchy

```text
OpenAPIError
 └── HTTPExecutionError
      ├── AuthenticationError
      ├── RequestValidationError
      ├── ResponseParsingError
      └── ExecutionTimeoutError
```

### 3.6 Authentication Provider

The **Authentication Provider** manages auth headers and query parameters dynamically. It supports multiple authentication schemes (API Key, HTTP Bearer, HTTP Basic, OAuth2) and securely injects credentials into outbound HTTP requests without exposing secret values to the LLM agent or tool definitions.

### 3.7 Tool Generator

The **Tool Generator** acts as the high-level factory interface for end users. It converts parsed operations into `langchain_core.tools.BaseTool` instances. It supports configuration options such as filtering by HTTP method, operation tags, or path patterns, as well as customizing tool naming conventions and prompt description templates.

---

## 4. Data Flow

1. **Initialization**: The user passes an OpenAPI spec source (path, URL, or dict) to the `OpenAPIToolset` factory.
2. **Ingestion & Parsing**: The `OpenAPI Loader` reads the spec, resolves reference pointers, and creates an immutable `OpenAPISpec` internal model.
3. **Tool Creation**:
   * For each selected operation in the specification, the `Schema Converter` builds a Pydantic input model (`args_schema`).
   * The `Tool Generator` constructs a native `BaseTool` wrapping the operation metadata, input schema, and bound `HTTP Executor`.
4. **Agent Invocation**:
   * An LLM agent invokes the tool with generated JSON arguments.
   * LangChain validates the arguments against the tool's Pydantic `args_schema`.
   * The tool forwards validated parameters to the `HTTP Executor`.
   * The `Authentication Provider` attaches necessary headers/credentials.
   * The `HTTP Executor` performs the request asynchronously and returns formatted response content back to the agent.

---

## 5. Future Extensibility

* **Custom Transport Adapters**: Ability to plug in alternative HTTP execution engines (e.g., custom `aiohttp` or enterprise proxy clients).
* **Response Summarizers / Truncators**: Middleware hooks to format or summarize large API responses before returning them to LLM context windows.
* **Custom Auth Handlers**: Support for enterprise authentication mechanisms like AWS SigV4 or custom HMAC header signing.
* **GraphQL / gRPC Adapters**: Future extension of the tool generator interface to support multi-protocol tool synthesis alongside OpenAPI.
