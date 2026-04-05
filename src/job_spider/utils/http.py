"""HTTP utilities for making requests."""

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class HttpResponse:
    """Wrapper for HTTP response."""

    status_code: int
    url: str
    content: bytes
    headers: dict[str, str]
    elapsed: float

    @property
    def text(self) -> str:
        """Get response text."""
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Parse response as JSON."""
        import json
        return json.loads(self.text)


class HttpClient:
    """HTTP client with middleware support."""

    def __init__(
        self,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        default_headers: dict[str, str] | None = None,
    ):
        """Initialize HTTP client.

        Args:
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow redirects
            default_headers: Default headers for all requests
        """
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
        )
        self.default_headers = default_headers or {}

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        """Make a GET request.

        Args:
            url: Request URL
            params: Query parameters
            headers: Request headers
            **kwargs: Additional httpx arguments

        Returns:
            HttpResponse object
        """
        merged_headers = {**self.default_headers, **(headers or {})}
        response = await self._client.get(url, params=params, headers=merged_headers, **kwargs)

        return HttpResponse(
            status_code=response.status_code,
            url=str(response.url),
            content=response.content,
            headers=dict(response.headers),
            elapsed=response.elapsed.total_seconds(),
        )

    async def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        """Make a POST request.

        Args:
            url: Request URL
            data: Form data
            json: JSON body
            headers: Request headers
            **kwargs: Additional httpx arguments

        Returns:
            HttpResponse object
        """
        merged_headers = {**self.default_headers, **(headers or {})}
        response = await self._client.post(url, data=data, json=json, headers=merged_headers, **kwargs)

        return HttpResponse(
            status_code=response.status_code,
            url=str(response.url),
            content=response.content,
            headers=dict(response.headers),
            elapsed=response.elapsed.total_seconds(),
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "HttpClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


def create_client(
    user_agent: str | None = None,
    proxy: str | None = None,
    **kwargs: Any,
) -> HttpClient:
    """Create an HTTP client with common settings.

    Args:
        user_agent: User-Agent header
        proxy: Proxy URL
        **kwargs: Additional arguments

    Returns:
        Configured HttpClient
    """
    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    if proxy:
        kwargs["proxies"] = {"http://": proxy, "https://": proxy}

    return HttpClient(default_headers=headers, **kwargs)
