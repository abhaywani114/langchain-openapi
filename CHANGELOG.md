# Changelog

All notable changes to `langchain-openapi` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
