# Changelog

All notable changes to `langchain-openapi` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Generic HTTP Toolkit (`GenericOpenAPIToolkit`)**: A new toolkit that exposes a *constant* set of tools — `GET`, `POST`, `PUT`, `PATCH`, `DELETE` plus discovery helpers (`search_operations`, `describe_operation`, `list_operations`, `list_tags`) — regardless of how many operations a spec declares. Ideal for very large APIs (GitHub, Kubernetes, Stripe) where per-operation typed tools would exhaust the prompt window. Reuses the entire existing execution stack (loader, parser, resolver, providers, middleware, executor, response parser).
- **In-Memory Operation Search Index (`OperationIndex`, `SearchResult`, `OperationEntry`)**: Keyword + fuzzy ranking over operationId, summary, description, tags, path, and method. No external vector database required.
- **Hybrid Mode**: Both `GenericOpenAPIToolkit.get_tools(mode="hybrid")` and `OpenAPIToolkit.get_tools(mode="hybrid", typed_tags=[...])` mix typed tools for selected operations with generic HTTP tools for the rest.
- **Raw Executor Endpoint**: `AsyncHTTPExecutor.request(method, endpoint, ...)` — a lower-level entry point that shares the provider + middleware pipeline with `execute()` and powers the generic HTTP tools.
- **Spec Adapter Architecture (`langchain_openapi_tools.adapters`)**: Introduced a `SpecAdapter` protocol plus concrete `Swagger2Adapter` and `OpenAPI3Adapter` implementations that provide a uniform pipeline entry for Swagger 2.0, OpenAPI 3.0.x, and OpenAPI 3.1.x documents. New public helpers: `detect_spec_version`, `select_adapter`, and `normalize_spec`. `OpenAPISpec.spec_family` records the source family, and `OpenAPISpec.from_dict` now routes through the adapter layer.
- **OpenAPI 3.1 Schema Support**: Parser and `SchemaConverter` now understand union `type` arrays (`["string", "null"]`), `const`, `oneOf` / `anyOf` (rendered as `typing.Union`), `allOf` (merged into a single Pydantic model), and the `readOnly` / `writeOnly` / `deprecated` field flags. `Schema` gained `const`, `one_of`, `any_of`, `all_of`, `read_only`, `write_only`, and `deprecated` attributes.
- **Full Media-Type Dispatch**: `RequestBuilder` now inspects each operation's declared `requestBody` content types and dispatches to the correct httpx encoding path — `application/json` (and `+json` vendor variants), `application/x-www-form-urlencoded`, `multipart/form-data` (with file-part support), `text/*`, and `application/xml`. Pydantic-model bodies produced by the dynamic args schema are coerced back to JSON-safe primitives before serialization. `BuiltRequest` gained `data`, `files`, and `content` fields.
- **Real-World Compatibility Tests**: Added `tests/test_adapters.py`, `tests/test_openapi_31.py`, `tests/test_media_types.py`, and `tests/test_compat_matrix.py` (Petstore, Crossref, GitHub, Stripe, Kubernetes, ASP.NET fakerestapi excerpts) exercising the full pipeline end-to-end via `respx`.

### Fixed
- **Base URL Resolution Across the Pipeline**: The specification's source URL is now propagated from `OpenAPILoader.from_url` → `OpenAPISpec` → `OpenAPIParser` → `RequestBuilder`. This closes an architectural gap where relative or missing `servers` entries produced relative request URLs.
  - OpenAPI 3.x specs that omit the `servers` block (e.g. `https://fakerestapi.azurewebsites.net/swagger/v1/swagger.json`) now default to the document's `scheme://host` origin, matching the OpenAPI 3.x specification.
  - OpenAPI 3.x relative server URLs (e.g. `"/api/v2"`) are resolved against the document location via `urllib.parse.urljoin`.
  - Swagger 2.0 specs that omit `host` fall back to the source URL's host and scheme.
  - `OpenAPISpec` gained a `source_url` field; `OpenAPISpec.from_dict` and `SwaggerNormalizer` accept an optional `source_url` argument for programmatic use.
  - Redundant Swagger normalization calls in `OpenAPILoader.load` and `OpenAPIParser.__init__` were removed — `OpenAPISpec.from_dict` is now the single normalization site.
- No changes to `RequestBuilder` or `AsyncHTTPExecutor` were required to fix base-URL resolution; they transparently receive an absolute base URL because `spec.servers[0]` is guaranteed absolute whenever the spec was loaded from a URL.

### Compatibility
- All previously public APIs (`OpenAPIToolkit`, `OpenAPILoader`, `OpenAPIParser`, `OpenAPISpec`, `SwaggerNormalizer`, `RequestBuilder`, `AsyncHTTPExecutor`, middleware, providers) retain their original signatures. New parameters (`source_url`, `spec_family`) are optional.

---

## [1.0.2] - 2026-08-01

### Fixed
- **Base URL Generation**: Fixed Swagger 2.0 base URL generation (e.g. Crossref host/basePath/schemes resolution) to prevent relative URL execution errors.
- **URL Resolution**: Updated `RequestBuilder` to use `urllib.parse.urljoin` for safe URL concatenation.

### Added
- **Package Naming Clarification**: Clarified PyPI package name (`langchain-openapi-tools`) vs import module name (`langchain_openapi`) across documentation.
- **Prompt Optimization & Config**: Introduced `OpenAPIToolkitConfig` for user-controlled description modes (`full`, `compact`, `minimal`) and description prompt compression (`compress_descriptions=True`).
- **Tool Description Customization**: Added `tool_description_overrides` dict and custom `description_builder` callback functions.
- **Operation & Tag Filtering**: Added tag filtering (`include_tags`, `exclude_tags`) and operation filtering (`include_operations`, `exclude_operations`) at initial toolkit construction level.

---

## [1.0.0] - 2026-08-01

### Added
- **First Production Release (v1.0.0)**.
- **OpenAPI Loader**: Load specs from remote URLs, local JSON/YAML files, or Python dictionaries.
- **OpenAPI Parser**: Strongly typed internal data models for operations, parameters, request bodies, and responses with local `$ref` resolution.
- **Schema Converter Engine**: Convert JSON Schema parameters and request bodies to dynamic Pydantic models at runtime with optional multi-page pagination controls.
- **Async HTTP Executor Engine**: Asynchronous execution using `httpx.AsyncClient` with dynamic parameter formatting and response parsing.
- **LangChain Tool Factory**: Convert OpenAPI operations into dynamic LangChain `StructuredTool` collections with filtering options.
- **Authentication & Request Providers**: Pluggable provider system (`BearerAuthProvider`, `APIKeyHeaderProvider`, `APIKeyQueryProvider`, `BasicAuthProvider`, `CompositeProvider`).
- **Production Middleware**: Onion-style pipeline (`RetryMiddleware`, `RateLimitMiddleware`, `CacheMiddleware`, `PaginationMiddleware`, `LoggingMiddleware`).
- **Documentation & Examples**: Comprehensive MkDocs site, complete example applications (Crossref, GitHub, Petstore, JSONPlaceholder), and benchmark suite.
- **CI/CD & Release Automation**: GitHub Actions for CI, Release generation, PyPI Trusted Publishing, and GitHub Pages deployment.
