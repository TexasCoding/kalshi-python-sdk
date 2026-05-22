"""Tests for #253: per-request ``extra_headers`` is reachable from every public
resource method.

* Three representative resources (orders, markets, portfolio) exercise the
  end-to-end wire delivery and the transport-level auth-header precedence
  guarantee (``KALSHI-ACCESS-*`` cannot be spoofed via ``extra_headers``).
* A single parametric test enumerates every public method on every
  ``SyncResource`` / ``AsyncResource`` subclass and asserts the ``extra_headers``
  kwarg exists with a ``None`` default.
"""

from __future__ import annotations

import inspect
import pkgutil
from typing import Any

import httpx
import pytest
import respx

from kalshi import KalshiClient
from kalshi.auth import KalshiAuth
from kalshi.config import DEMO_WS_URL, KalshiConfig
from kalshi.resources._base import AsyncResource, SyncResource
from tests._model_fixtures import market_dict, order_dict

MOCK_BASE = "https://demo-api.kalshi.co/trade-api/v2"


def _config(**overrides: Any) -> KalshiConfig:
    return KalshiConfig(
        base_url=MOCK_BASE,
        ws_base_url=DEMO_WS_URL,
        timeout=5.0,
        max_retries=0,
        **overrides,
    )


def _example_order_payload() -> dict[str, Any]:
    return order_dict(order_id="o1", ticker="BTC", side="yes", status="resting")


def _example_market_payload() -> dict[str, Any]:
    return market_dict(ticker="BTC")


class TestOrders:
    @respx.mock
    def test_create_order_threads_extra_headers(self, test_auth: KalshiAuth) -> None:
        route = respx.post(f"{MOCK_BASE}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _example_order_payload()})
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.orders.create(
                ticker="BTC",
                side="yes",
                action="buy",
                client_order_id="cli-1",
                count=1,
                yes_price=50,
                extra_headers={"Idempotency-Key": "abc"},
            )
        assert route.calls[0].request.headers["Idempotency-Key"] == "abc"

    @respx.mock
    def test_create_order_extra_headers_rejects_kalshi_access(self, test_auth: KalshiAuth) -> None:
        # #298: caller-supplied KALSHI-ACCESS-* keys now raise instead of
        # silently leaking onto the wire alongside the SDK-signed pair.
        respx.post(f"{MOCK_BASE}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _example_order_payload()})
        )
        with (
            KalshiClient(auth=test_auth, config=_config()) as client,
            pytest.raises(ValueError, match="KALSHI-ACCESS-"),
        ):
            client.orders.create(
                ticker="BTC",
                side="yes",
                action="buy",
                client_order_id="cli-1",
                count=1,
                yes_price=50,
                extra_headers={
                    "KALSHI-ACCESS-KEY": "spoofed",
                    "KALSHI-ACCESS-SIGNATURE": "spoofed-sig",
                    "KALSHI-ACCESS-TIMESTAMP": "0",
                },
            )

    @respx.mock
    def test_cancel_order_threads_extra_headers(self, test_auth: KalshiAuth) -> None:
        route = respx.delete(f"{MOCK_BASE}/portfolio/orders/o1").mock(
            return_value=httpx.Response(204)
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.orders.cancel("o1", extra_headers={"X-Trace": "t"})
        assert route.calls[0].request.headers["X-Trace"] == "t"


class TestMarkets:
    @respx.mock
    def test_get_market_threads_extra_headers(self, test_auth: KalshiAuth) -> None:
        route = respx.get(f"{MOCK_BASE}/markets/BTC").mock(
            return_value=httpx.Response(200, json={"market": _example_market_payload()})
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.markets.get("BTC", extra_headers={"X-Test": "v"})
        assert route.calls[0].request.headers["X-Test"] == "v"

    @respx.mock
    def test_get_market_extra_headers_rejects_kalshi_access(self, test_auth: KalshiAuth) -> None:
        respx.get(f"{MOCK_BASE}/markets/BTC").mock(
            return_value=httpx.Response(200, json={"market": _example_market_payload()})
        )
        with (
            KalshiClient(auth=test_auth, config=_config()) as client,
            pytest.raises(ValueError, match="KALSHI-ACCESS-"),
        ):
            client.markets.get("BTC", extra_headers={"KALSHI-ACCESS-KEY": "spoofed"})


class TestPortfolio:
    @respx.mock
    def test_get_balance_threads_extra_headers(self, test_auth: KalshiAuth) -> None:
        route = respx.get(f"{MOCK_BASE}/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 0,
                    "payout": 0,
                    "balance_dollars": "0.00",
                    "portfolio_value": 0,
                    "updated_ts": 0,
                },
            )
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.portfolio.balance(extra_headers={"X-Test": "v"})
        assert route.calls[0].request.headers["X-Test"] == "v"

    @respx.mock
    def test_balance_extra_headers_rejects_kalshi_access(self, test_auth: KalshiAuth) -> None:
        respx.get(f"{MOCK_BASE}/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 0,
                    "payout": 0,
                    "balance_dollars": "0.00",
                    "portfolio_value": 0,
                    "updated_ts": 0,
                },
            )
        )
        with (
            KalshiClient(auth=test_auth, config=_config()) as client,
            pytest.raises(ValueError, match="KALSHI-ACCESS-"),
        ):
            client.portfolio.balance(extra_headers={"KALSHI-ACCESS-KEY": "spoofed"})


# ---------------------------------------------------------------------------
# #298: KALSHI-ACCESS-* rejection, Content-Type pinning, header round-trip.
# ---------------------------------------------------------------------------


class TestHeaderCollision298:
    @respx.mock
    def test_extra_headers_lowercase_kalshi_access_raises(
        self, test_auth: KalshiAuth
    ) -> None:
        # Case-mismatched key (lowercase) was previously a forge surface; the
        # public boundary now raises ValueError naming the leaked key.
        respx.post(f"{MOCK_BASE}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _example_order_payload()})
        )
        with (
            KalshiClient(auth=test_auth, config=_config()) as client,
            pytest.raises(ValueError, match="kalshi-access-key"),
        ):
            client.orders.create(
                ticker="BTC",
                side="yes",
                action="buy",
                client_order_id="cli-1",
                count=1,
                yes_price=50,
                extra_headers={"kalshi-access-key": "X"},
            )

    @respx.mock
    def test_post_json_body_pins_content_type_against_caller_override(
        self, test_auth: KalshiAuth
    ) -> None:
        # Caller-supplied lowercase ``content-type`` must NOT win over the
        # JSON body's content-type, which the SDK pins at the body-helper
        # layer in resources/_base.py:_post.
        route = respx.post(f"{MOCK_BASE}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": _example_order_payload()})
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.orders.create(
                ticker="BTC",
                side="yes",
                action="buy",
                client_order_id="cli-1",
                count=1,
                yes_price=50,
                extra_headers={"content-type": "text/plain"},
            )
        wire = route.calls.last.request.headers
        assert wire["content-type"].startswith("application/json")
        # And only one Content-Type line went on the wire (case-insensitive).
        ct_lines = [k for k, _ in wire.raw if k.lower() == b"content-type"]
        assert len(ct_lines) == 1, ct_lines

    @respx.mock
    def test_extra_headers_non_auth_round_trips_unchanged(
        self, test_auth: KalshiAuth
    ) -> None:
        route = respx.get(f"{MOCK_BASE}/markets/BTC").mock(
            return_value=httpx.Response(200, json={"market": _example_market_payload()})
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.markets.get("BTC", extra_headers={"x-request-id": "abc"})
        wire = route.calls.last.request.headers
        assert wire["x-request-id"] == "abc"
        # And it appeared exactly once.
        rid_lines = [k for k, _ in wire.raw if k.lower() == b"x-request-id"]
        assert len(rid_lines) == 1, rid_lines

    @respx.mock
    def test_delete_with_body_sync_pins_content_type(self, test_auth: KalshiAuth) -> None:
        # #298 follow-up: bot review flagged that _delete_with_body (sync)
        # left Content-Type unspecified, so a stale config.extra_headers or
        # extra_headers={"content-type": "text/plain"} could ride on the wire
        # alongside a JSON body. Mirror the _post/_put guarantee.
        from kalshi.models.orders import BatchCancelOrdersV2Request

        route = respx.delete(
            f"{MOCK_BASE}/portfolio/events/orders/batched"
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.orders.batch_cancel_v2(
                request=BatchCancelOrdersV2Request(orders=[]),
                extra_headers={"content-type": "text/plain"},
            )
        wire = route.calls.last.request.headers
        assert wire["content-type"].startswith("application/json")
        ct_lines = [k for k, _ in wire.raw if k.lower() == b"content-type"]
        assert len(ct_lines) == 1, ct_lines

    async def test_delete_with_body_async_pins_content_type(
        self, test_auth: KalshiAuth
    ) -> None:
        # Async mirror of the sync wire-assertion above.
        import respx as _respx

        from kalshi import AsyncKalshiClient
        from kalshi.models.orders import BatchCancelOrdersV2Request

        with _respx.mock() as router:
            route = router.delete(
                f"{MOCK_BASE}/portfolio/events/orders/batched"
            ).mock(return_value=httpx.Response(200, json={"orders": []}))
            async with AsyncKalshiClient(auth=test_auth, config=_config()) as client:
                await client.orders.batch_cancel_v2(
                    request=BatchCancelOrdersV2Request(orders=[]),
                    extra_headers={"content-type": "text/plain"},
                )
            wire = route.calls.last.request.headers
            assert wire["content-type"].startswith("application/json")
            ct_lines = [k for k, _ in wire.raw if k.lower() == b"content-type"]
            assert len(ct_lines) == 1, ct_lines


# ---------------------------------------------------------------------------
# Parametric coverage — every public resource method has the kwarg.
# ---------------------------------------------------------------------------


def _collect_resource_methods() -> list[tuple[type, str, Any]]:
    import kalshi.resources as resources_pkg

    out: list[tuple[type, str, Any]] = []
    for info in pkgutil.iter_modules(resources_pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod = __import__(f"kalshi.resources.{info.name}", fromlist=["*"])
        for attr in dir(mod):
            cls = getattr(mod, attr)
            if not isinstance(cls, type):
                continue
            if cls.__module__ != mod.__name__:
                continue
            if not issubclass(cls, (SyncResource, AsyncResource)):
                continue
            for name, fn in inspect.getmembers(cls, predicate=inspect.isfunction):
                if name.startswith("_"):
                    continue
                # Skip methods inherited from the base (none have public methods,
                # but be defensive).
                if name not in cls.__dict__:
                    continue
                out.append((cls, name, fn))
    return out


_METHODS = _collect_resource_methods()


@pytest.mark.parametrize(
    "cls,name,fn",
    _METHODS,
    ids=[f"{c.__name__}.{n}" for c, n, _ in _METHODS],
)
def test_every_public_method_accepts_extra_headers(cls: type, name: str, fn: Any) -> None:
    sig = inspect.signature(fn)
    assert "extra_headers" in sig.parameters, f"{cls.__name__}.{name} missing extra_headers kwarg"
    param = sig.parameters["extra_headers"]
    assert param.default is None, (
        f"{cls.__name__}.{name} extra_headers default must be None, got {param.default!r}"
    )
    assert param.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )

# ---------------------------------------------------------------------------
# #313 + #341 — post-construction immutability and single header pipeline.
# ---------------------------------------------------------------------------


class TestExtraHeadersSecurityFreeze:
    @respx.mock
    def test_issue_313_extra_headers_post_mutation_does_not_send_auth_forge(
        self, test_auth: KalshiAuth
    ) -> None:
        # #313: the underlying mapping is frozen post-construction, so attempting
        # to seed a forged KALSHI-ACCESS-* key after construction must either
        # raise (TypeError on the proxy) or otherwise have no effect on the wire
        # — never both an SDK-signed and a caller-forged pair on the same line.
        cfg = _config(extra_headers={"X-Trace-Id": "t1"})
        with pytest.raises(TypeError):
            cfg.extra_headers["kalshi-access-key"] = "forged"  # type: ignore[index]

        route = respx.get(f"{MOCK_BASE}/markets/BTC").mock(
            return_value=httpx.Response(200, json={"market": _example_market_payload()})
        )
        with KalshiClient(auth=test_auth, config=cfg) as client:
            client.markets.get("BTC")
        wire = route.calls.last.request.headers
        # No forged lowercase pair ever reached the wire.
        forged = [k for k, _ in wire.raw if k.lower() == b"kalshi-access-key"]
        # Exactly one signed KALSHI-ACCESS-KEY line, never two.
        assert len(forged) == 1, forged
        # And the signed value is not the forged one.
        assert wire["KALSHI-ACCESS-KEY"] != "forged"

    @respx.mock
    def test_issue_341_extra_headers_single_pipeline(
        self, test_auth: KalshiAuth
    ) -> None:
        # #341: config.extra_headers is no longer attached to httpx.Client's
        # default headers. _ci_merge is the single source of truth, so a
        # per-call extra_headers value must override config.extra_headers
        # case-insensitively with no duplicate raw header line on the wire.
        cfg = _config(
            extra_headers={"X-Trace-Id": "config-default", "User-Agent": "kalshi-sdk/cfg"}
        )
        route = respx.get(f"{MOCK_BASE}/markets/BTC").mock(
            return_value=httpx.Response(200, json={"market": _example_market_payload()})
        )
        with KalshiClient(auth=test_auth, config=cfg) as client:
            # Per-call layer overrides the config layer (case-insensitive).
            client.markets.get(
                "BTC", extra_headers={"x-trace-id": "per-call"}
            )
            # No per-call override → config default reaches the wire.
            client.markets.get("BTC")

        first = route.calls[0].request.headers
        assert first["x-trace-id"] == "per-call"
        # Exactly one X-Trace-Id raw header line — no httpx-side duplicate
        # alongside the SDK-merged one.
        first_trace = [k for k, _ in first.raw if k.lower() == b"x-trace-id"]
        assert len(first_trace) == 1, first_trace
        # User-Agent from config still reaches both wires (single pipeline).
        assert first["user-agent"] == "kalshi-sdk/cfg"

        second = route.calls[1].request.headers
        assert second["x-trace-id"] == "config-default"
        second_trace = [k for k, _ in second.raw if k.lower() == b"x-trace-id"]
        assert len(second_trace) == 1, second_trace
