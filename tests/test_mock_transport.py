"""Tests for the record/replay mock transport layer."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from kalshi import KalshiClient
from kalshi.testing import (
    AsyncRecordingTransport,
    AsyncReplayTransport,
    FixtureNotFoundError,
    RecordingTransport,
    ReplayTransport,
)
from kalshi.testing._fixtures import fingerprint, fixture_filename


def _make_stub_transport(responses: dict[tuple[str, str], httpx.Response]) -> httpx.MockTransport:
    """Build an httpx.MockTransport that returns canned responses by (method, path)."""

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method.upper(), request.url.path)
        if key not in responses:
            raise AssertionError(f"unexpected request: {key}")
        # Return a fresh copy so reads don't interfere between calls.
        canned = responses[key]
        return httpx.Response(
            status_code=canned.status_code,
            headers=canned.headers,
            content=canned.content,
        )

    return httpx.MockTransport(handler)


class _AsyncStubTransport(httpx.AsyncBaseTransport):
    """Async transport stub — proper AsyncBaseTransport subtype so the typed
    ``real_transport: httpx.AsyncBaseTransport`` hint is satisfied without
    relying on ``httpx.MockTransport`` happening to implement both interfaces.
    """

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self._handler(request)


def test_fingerprint_ignores_headers_and_body() -> None:
    """Two requests differing only in headers/body produce the same fingerprint."""
    req_a = httpx.Request(
        "GET",
        "https://api.example.com/trade-api/v2/exchange/status?foo=1&bar=2",
        headers={"KALSHI-ACCESS-SIGNATURE": "abc", "KALSHI-ACCESS-TIMESTAMP": "111"},
    )
    req_b = httpx.Request(
        "GET",
        "https://api.example.com/trade-api/v2/exchange/status?bar=2&foo=1",
        headers={"KALSHI-ACCESS-SIGNATURE": "xyz", "KALSHI-ACCESS-TIMESTAMP": "222"},
    )
    assert fingerprint(req_a) == fingerprint(req_b)


def test_fingerprint_differs_on_method_or_path() -> None:
    base = "https://api.example.com/trade-api/v2/markets"
    g = httpx.Request("GET", base)
    p = httpx.Request("POST", base)
    other = httpx.Request("GET", base + "/ABC")
    assert fingerprint(g) != fingerprint(p)
    assert fingerprint(g) != fingerprint(other)


def test_record_then_replay_roundtrip(tmp_path: Path) -> None:
    """Record a session into a temp dir, then replay it and get the same response."""
    canned = httpx.Response(
        200,
        headers=[("content-type", "application/json")],
        content=json.dumps({"exchange_active": True, "trading_active": True}).encode("utf-8"),
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})

    fixtures_dir = tmp_path / "fixtures"

    # Record: drive a real-looking request through RecordingTransport (wrapping the stub).
    rec = RecordingTransport(fixtures_dir, real_transport=stub)
    with KalshiClient(transport=rec) as client:
        first = client.exchange.status()
    assert first.exchange_active is True

    # The fixture file should now exist with the expected name.
    expected_file = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    assert expected_file.exists()
    stored = json.loads(expected_file.read_text())
    assert isinstance(stored, list) and len(stored) == 1
    assert stored[0]["response"]["status_code"] == 200
    assert stored[0]["response"]["body"] == {"exchange_active": True, "trading_active": True}

    # Replay: now use the recorded fixtures with no real network.
    replay = ReplayTransport(fixtures_dir)
    with KalshiClient(transport=replay) as client:
        second = client.exchange.status()
    assert second.exchange_active is True


def test_replay_raises_when_no_fixture_matches(tmp_path: Path) -> None:
    """An unrecorded request must raise FixtureNotFoundError, not silently 404."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()

    replay = ReplayTransport(fixtures_dir)
    with (
        KalshiClient(transport=replay) as client,
        pytest.raises(FixtureNotFoundError, match="No fixture file for"),
    ):
        client.exchange.status()


def test_replay_raises_when_query_mismatches(tmp_path: Path) -> None:
    """Same path but different query → no match → clear error."""
    canned = httpx.Response(
        200, content=json.dumps({"markets": [], "cursor": ""}).encode("utf-8")
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/markets"): canned})
    fixtures_dir = tmp_path / "fixtures"

    # Record with status=open
    with KalshiClient(
        transport=RecordingTransport(fixtures_dir, real_transport=stub)
    ) as client:
        client.markets.list(status="open", limit=1)

    # Replay with status=closed → same path, different query → must raise.
    with (
        KalshiClient(transport=ReplayTransport(fixtures_dir)) as client,
        pytest.raises(FixtureNotFoundError, match="matches GET"),
    ):
        client.markets.list(status="closed", limit=1)


def test_replay_ignores_signature_drift(tmp_path: Path, pem_bytes: bytes) -> None:
    """Auth signature/timestamp drift between record & replay must not break matching.

    Uses the shared ``pem_bytes`` fixture from ``tests/conftest.py`` to mint
    throwaway credentials.
    """
    canned = httpx.Response(
        200, content=json.dumps({"exchange_active": True, "trading_active": True}).encode("utf-8")
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    fixtures_dir = tmp_path / "fixtures"

    # Record with no auth.
    with KalshiClient(
        transport=RecordingTransport(fixtures_dir, real_transport=stub)
    ) as client:
        client.exchange.status()

    # Replay with synthetic credentials → signature header is now present and different,
    # but the fingerprint ignores it.
    with KalshiClient(
        key_id="test-id",
        private_key=pem_bytes,
        transport=ReplayTransport(fixtures_dir),
    ) as client:
        resp = client.exchange.status()
    assert resp.exchange_active is True


def test_multiple_pairs_for_same_endpoint_replay_in_order(tmp_path: Path) -> None:
    """Two recordings of the same endpoint should be replayed FIFO."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    file_path = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    pairs = [
        {
            "request": {
                "method": "GET",
                "url": "https://x/trade-api/v2/exchange/status",
                "path": "/trade-api/v2/exchange/status",
                "query": [],
            },
            "response": {
                "status_code": 200,
                "headers": [],
                "body_kind": "json",
                "body": {"exchange_active": True, "trading_active": True},
            },
        },
        {
            "request": {
                "method": "GET",
                "url": "https://x/trade-api/v2/exchange/status",
                "path": "/trade-api/v2/exchange/status",
                "query": [],
            },
            "response": {
                "status_code": 200,
                "headers": [],
                "body_kind": "json",
                "body": {"exchange_active": False, "trading_active": False},
            },
        },
    ]
    file_path.write_text(json.dumps(pairs))

    replay = ReplayTransport(fixtures_dir)
    with KalshiClient(transport=replay) as client:
        first = client.exchange.status()
        second = client.exchange.status()
    assert first.exchange_active is True
    assert second.exchange_active is False


@pytest.mark.asyncio
async def test_async_record_then_replay_roundtrip(tmp_path: Path) -> None:
    from kalshi import AsyncKalshiClient

    canned = httpx.Response(
        200, content=json.dumps({"exchange_active": True, "trading_active": True}).encode("utf-8")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/trade-api/v2/exchange/status"
        return httpx.Response(
            status_code=canned.status_code,
            headers=canned.headers,
            content=canned.content,
        )

    async_stub = _AsyncStubTransport(handler)
    fixtures_dir = tmp_path / "fixtures"

    rec = AsyncRecordingTransport(fixtures_dir, real_transport=async_stub)
    async with AsyncKalshiClient(transport=rec) as client:
        first = await client.exchange.status()
    assert first.exchange_active is True

    replay = AsyncReplayTransport(fixtures_dir)
    async with AsyncKalshiClient(transport=replay) as client:
        second = await client.exchange.status()
    assert second.exchange_active is True


@pytest.mark.asyncio
async def test_async_replay_raises_when_no_fixture(tmp_path: Path) -> None:
    from kalshi import AsyncKalshiClient

    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()

    async with AsyncKalshiClient(transport=AsyncReplayTransport(fixtures_dir)) as client:
        with pytest.raises(FixtureNotFoundError):
            await client.exchange.status()


def test_multiple_pairs_wrap_around_after_exhaustion(tmp_path: Path) -> None:
    """A third call to a 2-pair fixture wraps to pair 0 rather than raising.

    Documents the loop-on-exhaustion behavior promised by ``_find_match``.
    """
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    file_path = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")

    def _pair(exchange_active: bool) -> dict[str, object]:
        return {
            "request": {
                "method": "GET",
                "url": "https://x/trade-api/v2/exchange/status",
                "path": "/trade-api/v2/exchange/status",
                "query": [],
            },
            "response": {
                "status_code": 200,
                "headers": [],
                "body_kind": "json",
                "body": {"exchange_active": exchange_active, "trading_active": exchange_active},
            },
        }

    file_path.write_text(json.dumps([_pair(True), _pair(False)]))

    with KalshiClient(transport=ReplayTransport(fixtures_dir)) as client:
        first = client.exchange.status()
        second = client.exchange.status()
        third = client.exchange.status()  # exhausted both — must wrap to pair 0
    assert first.exchange_active is True
    assert second.exchange_active is False
    assert third.exchange_active is True


def test_replay_raises_on_malformed_fixture_file(tmp_path: Path) -> None:
    """A fixture file whose JSON root is not a list must surface a clear error,
    not silently degrade to "no matches"."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    file_path = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    file_path.write_text(json.dumps({"not": "a list"}))

    with (
        KalshiClient(transport=ReplayTransport(fixtures_dir)) as client,
        pytest.raises(ValueError),
    ):
        client.exchange.status()


def test_recording_transport_close_propagates_to_real_transport(tmp_path: Path) -> None:
    """``RecordingTransport.close()`` must close the wrapped real transport
    so callers don't leak connections."""
    closed = {"value": False}

    class TrackingTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("not called in this test")

        def close(self) -> None:
            closed["value"] = True

    rec = RecordingTransport(tmp_path, real_transport=TrackingTransport())
    rec.close()
    assert closed["value"] is True


@pytest.mark.asyncio
async def test_async_recording_transport_aclose_propagates(tmp_path: Path) -> None:
    """``AsyncRecordingTransport.aclose()`` must await the wrapped real
    transport's aclose so callers don't leak connections. Mirrors the
    sync sibling.
    """
    closed = {"value": False}

    class TrackingAsyncTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(
            self, request: httpx.Request
        ) -> httpx.Response:  # pragma: no cover
            raise AssertionError("not called in this test")

        async def aclose(self) -> None:
            closed["value"] = True

    rec = AsyncRecordingTransport(tmp_path, real_transport=TrackingAsyncTransport())
    await rec.aclose()
    assert closed["value"] is True
