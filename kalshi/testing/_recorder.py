"""Recording transports — proxy real requests and persist them to disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from kalshi.testing._fixtures import (
    fingerprint,
    load_pairs,
    record_pair,
    save_pairs,
)


class _RecorderBuffer:
    """Session-scoped in-memory buffer of recorded pairs, keyed by (method, path).

    Avoids the prior O(N²) load → append → save loop (#105). Existing on-disk
    pairs are loaded lazily once per (method, path); new pairs accumulate in
    memory and the full list is flushed on ``close()``.
    """

    def __init__(self, dir_path: Path) -> None:
        self._dir = dir_path
        self._pairs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        # Dirty key set so close() only rewrites files we actually touched.
        self._dirty: set[tuple[str, str]] = set()

    def append(self, method: str, path: str, pair: dict[str, Any]) -> None:
        key = (method, path)
        if key not in self._pairs:
            # Preserve any prior recordings on disk so re-entering the same
            # fixtures dir extends rather than replaces.
            self._pairs[key] = load_pairs(self._dir, method, path)
        self._pairs[key].append(pair)
        self._dirty.add(key)

    def flush(self) -> None:
        for key in self._dirty:
            method, path = key
            save_pairs(self._dir, method, path, self._pairs[key])
        self._dirty.clear()


class RecordingTransport(httpx.BaseTransport):
    """Sync httpx transport that proxies real requests and records each pair to disk.

    Wraps any underlying `httpx.BaseTransport` (defaults to a fresh
    `httpx.HTTPTransport`) so real network calls go through, while every
    request/response pair is buffered in memory and flushed to disk on
    ``close()`` — see #105 for the prior O(N²) per-request rewrite this fixes.
    """

    def __init__(
        self,
        dir_path: str | Path,
        *,
        real_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._dir = Path(dir_path)
        self._real = real_transport if real_transport is not None else httpx.HTTPTransport()
        self._buffer = _RecorderBuffer(self._dir)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._real.handle_request(request)
        # httpx streams response bodies; read so we can serialize the full body.
        response.read()
        method, path, _query = fingerprint(request)
        # Append to in-memory buffer; flushed to disk on close().
        # Recordings are expected to run sequentially (see module docstring).
        self._buffer.append(method, path, record_pair(request, response))
        return response

    def close(self) -> None:
        try:
            self._buffer.flush()
        finally:
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
        self._buffer = _RecorderBuffer(self._dir)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._real.handle_async_request(request)
        await response.aread()
        method, path, _query = fingerprint(request)
        self._buffer.append(method, path, record_pair(request, response))
        return response

    async def aclose(self) -> None:
        try:
            self._buffer.flush()
        finally:
            await self._real.aclose()
