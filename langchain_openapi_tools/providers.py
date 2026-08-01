"""Authentication and request mutation providers."""

import base64
import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import httpx

from langchain_openapi_tools.exceptions import AuthenticationError, ProviderError

logger = logging.getLogger(__name__)


@runtime_checkable
class RequestProvider(Protocol):
    """Protocol defining the interface for request providers."""

    async def apply(self, request: httpx.Request) -> httpx.Request:
        """Apply authentication or request mutations to an httpx.Request."""
        ...


class NoAuthProvider(RequestProvider):
    """Default pass-through provider that performs no request mutations."""

    async def apply(self, request: httpx.Request) -> httpx.Request:
        return request


class BearerAuthProvider(RequestProvider):
    """HTTP Bearer Token authentication provider."""

    def __init__(self, token: str) -> None:
        if not token or not token.strip():
            raise AuthenticationError("Bearer token cannot be empty.")
        self.token = token.strip()

    async def apply(self, request: httpx.Request) -> httpx.Request:
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request


class APIKeyHeaderProvider(RequestProvider):
    """API Key authentication injected via HTTP Header."""

    def __init__(self, key: str, header: str = "X-API-Key") -> None:
        if not key or not key.strip():
            raise AuthenticationError("API key cannot be empty.")
        if not header or not header.strip():
            raise AuthenticationError("Header name cannot be empty.")

        self.key = key.strip()
        self.header = header.strip()

    async def apply(self, request: httpx.Request) -> httpx.Request:
        request.headers[self.header] = self.key
        return request


class APIKeyQueryProvider(RequestProvider):
    """API Key authentication injected via Query Parameter."""

    def __init__(self, key: str, parameter: str = "api_key") -> None:
        if not key or not key.strip():
            raise AuthenticationError("API key cannot be empty.")
        if not parameter or not parameter.strip():
            raise AuthenticationError("Query parameter name cannot be empty.")

        self.key = key.strip()
        self.parameter = parameter.strip()

    async def apply(self, request: httpx.Request) -> httpx.Request:
        params = dict(request.url.params)
        params[self.parameter] = self.key
        request.url = request.url.copy_with(params=params)
        return request


class BasicAuthProvider(RequestProvider):
    """HTTP Basic authentication provider."""

    def __init__(self, username: str, password: str) -> None:
        if username is None or password is None:
            raise AuthenticationError("Username and password cannot be None.")

        user_pass = f"{username}:{password}".encode()
        self.encoded = base64.b64encode(user_pass).decode("ascii")

    async def apply(self, request: httpx.Request) -> httpx.Request:
        request.headers["Authorization"] = f"Basic {self.encoded}"
        return request


class StaticHeadersProvider(RequestProvider):
    """Request provider that injects arbitrary static headers."""

    def __init__(self, headers: dict[str, str]) -> None:
        if not isinstance(headers, dict):
            raise ProviderError("Headers must be provided as a dictionary.")
        self.headers = {k: str(v) for k, v in headers.items()}

    async def apply(self, request: httpx.Request) -> httpx.Request:
        for k, v in self.headers.items():
            request.headers[k] = v
        return request


class CookiesProvider(RequestProvider):
    """Request provider for injecting HTTP cookies into requests."""

    def __init__(self, cookies: dict[str, str]) -> None:
        if not isinstance(cookies, dict):
            raise ProviderError("Cookies must be provided as a dictionary.")
        self.cookies = {k: str(v) for k, v in cookies.items()}

    async def apply(self, request: httpx.Request) -> httpx.Request:
        if not self.cookies:
            return request

        existing_cookie_hdr = request.headers.get("cookie", "")
        parsed_cookies: dict[str, str] = {}

        if existing_cookie_hdr:
            for pair in existing_cookie_hdr.split(";"):
                if "=" in pair:
                    ck, cv = pair.strip().split("=", 1)
                    parsed_cookies[ck] = cv

        parsed_cookies.update(self.cookies)
        request.headers["Cookie"] = "; ".join(
            f"{k}={v}" for k, v in parsed_cookies.items()
        )
        return request


class CompositeProvider(RequestProvider):
    """Composite provider for executing a sequence of RequestProviders in order."""

    def __init__(self, providers: Sequence[RequestProvider]) -> None:
        if not isinstance(providers, (list, tuple)) or isinstance(
            providers, (str, bytes)
        ):
            raise ProviderError(
                "Providers must be a list or tuple of RequestProviders."
            )
        self.providers = list(providers)

    async def apply(self, request: httpx.Request) -> httpx.Request:
        current_request = request
        for provider in self.providers:
            try:
                current_request = await provider.apply(current_request)
            except (AuthenticationError, ProviderError):
                raise
            except Exception as exc:
                logger.error(
                    "Provider '%s' failed during request application: %s", provider, exc
                )
                raise ProviderError(
                    f"Request provider execution failed: {exc}"
                ) from exc

        return current_request
