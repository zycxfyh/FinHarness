from __future__ import annotations

import asyncio
from typing import Any

import httpx


class AsgiTestClient:
    """Small sync wrapper around httpx ASGITransport for unittest tests.

    Starlette 1.3.1's deprecated httpx-backed TestClient can hang in this
    environment when httpx2 is not installed. This keeps tests on the real ASGI
    route stack without adding another dependency.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return asyncio.run(self._request("GET", path, **kwargs))

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return asyncio.run(self._request("POST", path, **kwargs))

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return asyncio.run(self._request("PATCH", path, **kwargs))

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    def close(self) -> None:
        return None
