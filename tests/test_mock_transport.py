"""Tests for the record/replay mock transport layer."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from kalshi import KalshiClient
from kalshi.errors import KalshiServerError
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


def test_recording_transport_buffers_until_close(tmp_path: Path) -> None:
    """Regression for #105: many requests to one endpoint must not rewrite the
    fixture file on every request. Count save_pairs calls — should be exactly
    one per (method, path) at flush time, not one per request."""
    import kalshi.testing._recorder as _rec

    canned = httpx.Response(
        200,
        headers=[("content-type", "application/json")],
        content=json.dumps({"exchange_active": True, "trading_active": True}).encode("utf-8"),
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    fixtures_dir = tmp_path / "fixtures"

    save_calls: list[tuple[str, str, int]] = []
    real_save = _rec.save_pairs

    def counting_save(dir_path: Path, method: str, path: str, pairs: list[Any]) -> None:
        save_calls.append((method, path, len(pairs)))
        real_save(dir_path, method, path, pairs)

    monkey_target = _rec
    monkey_target.save_pairs = counting_save  # type: ignore[assignment]
    try:
        rec = RecordingTransport(fixtures_dir, real_transport=stub)
        with KalshiClient(transport=rec) as client:
            for _ in range(50):
                client.exchange.status()
            # No flush yet — buffer holds pairs in memory.
            assert save_calls == []
        # Client context exit → transport close → single flush per touched key.
        assert save_calls == [("GET", "/trade-api/v2/exchange/status", 50)]
    finally:
        monkey_target.save_pairs = real_save  # type: ignore[assignment]

    # On-disk fixture must contain all 50 pairs, replayable end-to-end.
    expected_file = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    stored = json.loads(expected_file.read_text())
    assert len(stored) == 50


def test_recording_transport_extends_prior_session(tmp_path: Path) -> None:
    """Re-recording into the same fixtures dir must append to prior pairs,
    not clobber them — preserves the original load → append → save semantics."""
    canned = httpx.Response(
        200,
        headers=[("content-type", "application/json")],
        content=json.dumps({"exchange_active": True, "trading_active": True}).encode("utf-8"),
    )
    fixtures_dir = tmp_path / "fixtures"

    stub1 = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    with KalshiClient(transport=RecordingTransport(fixtures_dir, real_transport=stub1)) as c:
        c.exchange.status()

    stub2 = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    with KalshiClient(transport=RecordingTransport(fixtures_dir, real_transport=stub2)) as c:
        c.exchange.status()
        c.exchange.status()

    expected_file = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    stored = json.loads(expected_file.read_text())
    assert len(stored) == 3


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


# ---------------------------------------------------------------------------
# Non-JSON body coverage (#100 — F-Q-08)
#
# Real-world recordings will eventually capture an HTML 502 from a CDN/proxy,
# plus other non-JSON content types (plain text, octet-stream). The recorder
# falls back to ``body_kind="text"`` for any body json.loads can't parse. These
# tests prove that path round-trips cleanly and replays without corruption.
# ---------------------------------------------------------------------------


_HTML_502 = b"<html><body>502 Bad Gateway</body></html>"


def test_record_non_json_html_body_persists_as_text(tmp_path: Path) -> None:
    """A 502 with text/html body must serialize with body_kind=text and the
    HTML preserved verbatim — no JSON-parse crash, no header loss."""
    canned = httpx.Response(
        502,
        content=_HTML_502,
        headers=[("content-type", "text/html")],
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    fixtures_dir = tmp_path / "fixtures"

    # Drive the request through the recorder. Set max_retries=0 so the SDK
    # doesn't retry the 502 and pile up duplicate pairs.
    rec = RecordingTransport(fixtures_dir, real_transport=stub)
    with KalshiClient(transport=rec, max_retries=0) as client, pytest.raises(KalshiServerError):
        client.exchange.status()

    expected_file = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    stored = json.loads(expected_file.read_text())
    assert len(stored) == 1
    resp = stored[0]["response"]
    assert resp["status_code"] == 502
    assert resp["body_kind"] == "text"
    # HTML body round-trips byte-for-byte through the latin-1 fallback.
    assert resp["body"] == _HTML_502.decode("latin-1")
    # Content-Type header must survive recording so replay can rebuild it.
    headers = {k.lower(): v for k, v in resp["headers"]}
    assert headers.get("content-type") == "text/html"


def test_replay_non_json_html_body_surfaces_server_error(tmp_path: Path) -> None:
    """Replaying a recorded HTML 502 must reconstruct the same status + body
    so the client raises KalshiServerError with the HTML payload visible."""
    canned = httpx.Response(
        502,
        content=_HTML_502,
        headers=[("content-type", "text/html")],
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    fixtures_dir = tmp_path / "fixtures"

    with KalshiClient(
        transport=RecordingTransport(fixtures_dir, real_transport=stub),
        max_retries=0,
    ) as client, pytest.raises(KalshiServerError):
        client.exchange.status()

    # Now replay from disk — no real network, no stub. Must surface the same
    # 502 with the HTML body in the error message.
    with (
        KalshiClient(transport=ReplayTransport(fixtures_dir), max_retries=0) as client,
        pytest.raises(KalshiServerError) as exc_info,
    ):
        client.exchange.status()

    assert exc_info.value.status_code == 502
    # The HTML payload is the error "message" since the body is not JSON.
    assert "502 Bad Gateway" in str(exc_info.value)


def test_record_non_json_plain_text_body_persists_as_text(tmp_path: Path) -> None:
    """A 503 with text/plain body (no JSON anywhere) also takes the text branch."""
    body = b"Service Unavailable\nRetry in a bit."
    canned = httpx.Response(
        503,
        content=body,
        headers=[("content-type", "text/plain; charset=utf-8")],
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    fixtures_dir = tmp_path / "fixtures"

    rec = RecordingTransport(fixtures_dir, real_transport=stub)
    with KalshiClient(transport=rec, max_retries=0) as client, pytest.raises(KalshiServerError):
        client.exchange.status()

    expected_file = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    stored = json.loads(expected_file.read_text())
    resp = stored[0]["response"]
    assert resp["status_code"] == 503
    assert resp["body_kind"] == "text"
    assert resp["body"] == body.decode("latin-1")


def test_record_non_json_binary_body_persists_as_text(tmp_path: Path) -> None:
    """A non-UTF-8 octet-stream body must not crash the recorder — the latin-1
    fallback round-trips every byte 0x00-0xFF losslessly."""
    body = bytes(range(256))  # every possible byte, including invalid UTF-8 sequences
    canned = httpx.Response(
        502,
        content=body,
        headers=[("content-type", "application/octet-stream")],
    )
    stub = _make_stub_transport({("GET", "/trade-api/v2/exchange/status"): canned})
    fixtures_dir = tmp_path / "fixtures"

    rec = RecordingTransport(fixtures_dir, real_transport=stub)
    with KalshiClient(transport=rec, max_retries=0) as client, pytest.raises(KalshiServerError):
        client.exchange.status()

    expected_file = fixtures_dir / fixture_filename("GET", "/trade-api/v2/exchange/status")
    stored = json.loads(expected_file.read_text())
    resp = stored[0]["response"]
    assert resp["body_kind"] == "text"
    # latin-1 round-trip must reproduce the original bytes exactly.
    assert resp["body"].encode("latin-1") == body

    # And replay must rebuild the same body bytes — proving build_response's
    # text branch is the inverse of _response_to_dict's text branch.
    replay = ReplayTransport(fixtures_dir)
    with KalshiClient(transport=replay, max_retries=0) as client, pytest.raises(KalshiServerError):
        client.exchange.status()


class TestResponseHeaderFilter:
    """P1.5: RecordingTransport response_header_filter parameter."""

    def test_default_filter_drops_set_cookie(self, tmp_path: Path) -> None:
        """Default filter scrubs Set-Cookie / Authorization / X-Kalshi-* identity headers."""
        stub = _make_stub_transport(
            {
                ("GET", "/trade-api/v2/markets"): httpx.Response(
                    200,
                    headers=[
                        ("Content-Type", "application/json"),
                        ("Set-Cookie", "session=abcd; HttpOnly"),
                        ("Authorization", "Bearer should-not-be-recorded"),
                        ("X-Kalshi-User-Id", "uid-42"),
                        ("X-Kalshi-Trace-Account-Hash", "acc-99"),
                        ("X-Kalshi-Trace-Latency-Ms", "12"),  # NOT scrubbed by default
                        ("X-RateLimit-Remaining", "499"),  # NOT scrubbed by default
                    ],
                    content=b'{"markets": []}',
                )
            }
        )
        rec = RecordingTransport(tmp_path, real_transport=stub)
        try:
            with KalshiClient(transport=rec) as client:
                client.markets.list()
        finally:
            rec.close()
        # Read back the persisted fixture and check header set.
        fixture_file = tmp_path / fixture_filename("GET", "/trade-api/v2/markets")
        data = json.loads(fixture_file.read_text())
        # httpx normalises response header names to lowercase.
        headers = {k.lower(): v for k, v in data[0]["response"]["headers"]}
        # Defaults dropped (matched case-insensitively by the predicate):
        assert "set-cookie" not in headers
        assert "authorization" not in headers
        assert "x-kalshi-user-id" not in headers
        assert "x-kalshi-trace-account-hash" not in headers
        # Defaults preserved:
        assert headers.get("content-type") == "application/json"
        assert headers.get("x-ratelimit-remaining") == "499"
        # X-Kalshi-Request-Id also matches the default regex (the *-id suffix),
        # so request IDs are scrubbed too. Latency-Ms doesn't match any suffix
        # token and is preserved.
        assert headers.get("x-kalshi-request-id") is None
        assert headers.get("x-kalshi-trace-latency-ms") == "12"

    def test_custom_filter_callable_invoked(self, tmp_path: Path) -> None:
        """User-supplied predicate sees (name, value) and decides drop/keep."""
        calls: list[tuple[str, str]] = []

        def drop_secret_headers(name: str, value: str) -> bool:
            calls.append((name, value))
            return name.lower() == "x-secret"

        stub = _make_stub_transport(
            {
                ("GET", "/trade-api/v2/markets"): httpx.Response(
                    200,
                    headers=[
                        ("Content-Type", "application/json"),
                        ("X-Secret", "topsecret"),
                        ("Set-Cookie", "should-be-kept-when-filter-is-overridden"),
                    ],
                    content=b'{"markets": []}',
                )
            }
        )
        rec = RecordingTransport(
            tmp_path, real_transport=stub, response_header_filter=drop_secret_headers
        )
        try:
            with KalshiClient(transport=rec) as client:
                client.markets.list()
        finally:
            rec.close()
        # Predicate was called for every response header.
        # Predicate was called for every response header (httpx lowercases).
        seen_names = {name.lower() for name, _ in calls}
        assert "x-secret" in seen_names
        assert "set-cookie" in seen_names
        fixture_file = tmp_path / fixture_filename("GET", "/trade-api/v2/markets")
        data = json.loads(fixture_file.read_text())
        headers = {k.lower(): v for k, v in data[0]["response"]["headers"]}
        # Custom filter dropped X-Secret …
        assert "x-secret" not in headers
        # … and the default Set-Cookie scrubbing did NOT apply (user took over).
        assert headers.get("set-cookie") == "should-be-kept-when-filter-is-overridden"

    def test_iterable_deny_list_drops_matching_headers(self, tmp_path: Path) -> None:
        """Iterable[str] denylist is matched case-insensitively."""
        stub = _make_stub_transport(
            {
                ("GET", "/trade-api/v2/markets"): httpx.Response(
                    200,
                    headers=[
                        ("Content-Type", "application/json"),
                        ("X-Trace-ID", "abc"),
                        ("X-Keep-Me", "yes"),
                    ],
                    content=b'{"markets": []}',
                )
            }
        )
        rec = RecordingTransport(
            tmp_path, real_transport=stub, response_header_filter=["x-trace-id"]
        )
        try:
            with KalshiClient(transport=rec) as client:
                client.markets.list()
        finally:
            rec.close()
        fixture_file = tmp_path / fixture_filename("GET", "/trade-api/v2/markets")
        data = json.loads(fixture_file.read_text())
        headers = {k.lower(): v for k, v in data[0]["response"]["headers"]}
        assert "x-trace-id" not in headers
        assert headers.get("x-keep-me") == "yes"
