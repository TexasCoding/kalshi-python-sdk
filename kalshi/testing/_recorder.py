"""Recording transports — proxy real requests and persist them to disk."""

from __future__ import annotations

from pathlib import Path

import httpx

from kalshi.testing._fixtures import (
    fingerprint,
    load_pairs,
    record_pair,
    save_pairs,
)


class RecordingTransport(httpx.BaseTransport):
    """Sync httpx transport that proxies real requests and records each pair to disk.

    Wraps any underlying `httpx.BaseTransport` (defaults to a fresh
    `httpx.HTTPTransport`) so real network calls go through, while every
    request/response pair is appended to a JSON file under ``dir_path``.
    """

    def __init__(
        self,
        dir_path: str | Path,
        *,
        real_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._dir = Path(dir_path)
        self._real = real_transport if real_transport is not None else httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._real.handle_request(request)
        # httpx streams response bodies; read so we can serialize the full body.
        response.read()
        method, path, _query = fingerprint(request)
        # load → append → save is not atomic across concurrent requests to the
        # same endpoint. Recordings are expected to run sequentially.
        pairs = load_pairs(self._dir, method, path)
        pairs.append(record_pair(request, response))
        save_pairs(self._dir, method, path, pairs)
        return response

    def close(self) -> None:
        self._real.close()


class AsyncRecordingTransport(httpx.AsyncBaseTransport):
    """Async equivalent of :class:`RecordingTransport`."""

    def __init__(
        self,
        dir_path: str | Path,
        *,
        real_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._dir = Path(dir_path)
        self._real = (
            real_transport if real_transport is not None else httpx.AsyncHTTPTransport()
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._real.handle_async_request(request)
        await response.aread()
        method, path, _query = fingerprint(request)
        # load → append → save is not atomic across concurrent requests to the
        # same endpoint. Recordings are expected to run sequentially.
        pairs = load_pairs(self._dir, method, path)
        pairs.append(record_pair(request, response))
        save_pairs(self._dir, method, path, pairs)
        return response

    async def aclose(self) -> None:
        await self._real.aclose()
