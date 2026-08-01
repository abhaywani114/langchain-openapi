# AsyncHTTPExecutor API Reference

`AsyncHTTPExecutor` exposes two entry points that share the same
provider + middleware pipeline:

- `execute(operation, arguments)` — used by the typed
  [`OpenAPIToolkit`][langchain_openapi_tools.toolkit.OpenAPIToolkit] to
  dispatch a parsed :class:`Operation`.
- `request(method, endpoint, ...)` — the raw request path used by the
  [`GenericOpenAPIToolkit`][langchain_openapi_tools.generic_toolkit.GenericOpenAPIToolkit]
  so the generic `GET`/`POST`/... tools inherit authentication, retries,
  rate limiting, caching, and logging without duplication.

::: langchain_openapi_tools.executor.AsyncHTTPExecutor
::: langchain_openapi_tools.executor.RequestBuilder
::: langchain_openapi_tools.executor.BuiltRequest
::: langchain_openapi_tools.executor.ResponseData
::: langchain_openapi_tools.executor.ResponseParser
