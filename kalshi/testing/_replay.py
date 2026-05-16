"""Replay transports — serve previously recorded responses from disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from kalshi.testing._fixtures import build_response, fingerprint, load_pairs


class FixtureNotFoundError(LookupError):
    """Raised when no recorded fixture matches an incoming request."""


def _find_match(
    pairs: list[dict[str, Any]],
    method: str,
    path: str,
    query: tuple[tuple[str, str], ...],
    used: set[int],
) -> int | None:
    """Return the index of the first matching, not-yet-used pair, or None.

    Falls back to the first matching pair regardless of `used` if all matches are
    exhausted — replays loop rather than failing on repeated identical calls.
    """
    matches: list[int] = []
    for idx, pair in enumerate(pairs):
        req = pair.get("request", {})
        stored_method = str(req.get("method", "")).upper()
        stored_path = str(req.get("path", ""))
        stored_query = tuple(sorted(tuple(p) for p in req.get("query", [])))
        if stored_method == method and stored_path == path and stored_query == query:
            matches.append(idx)
    if not matches:
        return None
    for idx in matches:
        if idx not in used:
            return idx
    return matches[0]


class ReplayTransport(httpx.BaseTransport):
    """Sync httpx transport that serves responses from a directory of fixtures.

    Reads JSON fixture files written by :class:`RecordingTransport`. Requests are
    matched by HTTP method, URL path, and sorted query parameters (body and auth
    headers are ignored).

    Raises :class:`FixtureNotFoundError` when no matching fixture exists — never
    returns a synthetic 404 silently.
    """

    def __init__(self, dir_path: str | Path) -> None:
        self._dir = Path(dir_path)
        self._used: dict[tuple[str, str], set[int]] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        method, path, query = fingerprint(request)
        pairs = load_pairs(self._dir, method, path)
        if not pairs:
            raise FixtureNotFoundError(
                f"No fixture file for {method} {path}. "
                f"Expected file under {self._dir} — record one first."
            )
        used = self._used.setdefault((method, path), set())
        idx = _find_match(pairs, method, path, query, used)
        if idx is None:
            raise FixtureNotFoundError(
                f"No recorded response in {self._dir} matches {method} {path} "
                f"with query {list(query)}. Record this call first."
            )
        used.add(idx)
        return build_response(pairs[idx], request)

    def close(self) -> None:
        return None


class AsyncReplayTransport(httpx.AsyncBaseTransport):
    """Async equivalent of :class:`ReplayTransport`."""

    def __init__(self, dir_path: str | Path) -> None:
        self._dir = Path(dir_path)
        self._used: dict[tuple[str, str], set[int]] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        method, path, query = fingerprint(request)
        pairs = load_pairs(self._dir, method, path)
        if not pairs:
            raise FixtureNotFoundError(
                f"No fixture file for {method} {path}. "
                f"Expected file under {self._dir} — record one first."
            )
        used = self._used.setdefault((method, path), set())
        idx = _find_match(pairs, method, path, query, used)
        if idx is None:
            raise FixtureNotFoundError(
                f"No recorded response in {self._dir} matches {method} {path} "
                f"with query {list(query)}. Record this call first."
            )
        used.add(idx)
        return build_response(pairs[idx], request)

    async def aclose(self) -> None:
        return None
