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
    def test_create_order_extra_headers_cannot_override_auth(self, test_auth: KalshiAuth) -> None:
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
                extra_headers={
                    "KALSHI-ACCESS-KEY": "spoofed",
                    "KALSHI-ACCESS-SIGNATURE": "spoofed-sig",
                    "KALSHI-ACCESS-TIMESTAMP": "0",
                },
            )
        req = route.calls[0].request
        assert req.headers["KALSHI-ACCESS-KEY"] == "test-key-id"
        assert req.headers["KALSHI-ACCESS-SIGNATURE"] != "spoofed-sig"
        assert req.headers["KALSHI-ACCESS-TIMESTAMP"] != "0"

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
    def test_get_market_extra_headers_cannot_override_auth(self, test_auth: KalshiAuth) -> None:
        route = respx.get(f"{MOCK_BASE}/markets/BTC").mock(
            return_value=httpx.Response(200, json={"market": _example_market_payload()})
        )
        with KalshiClient(auth=test_auth, config=_config()) as client:
            client.markets.get("BTC", extra_headers={"KALSHI-ACCESS-KEY": "spoofed"})
        assert route.calls[0].request.headers["KALSHI-ACCESS-KEY"] == "test-key-id"


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
    def test_balance_extra_headers_cannot_override_auth(self, test_auth: KalshiAuth) -> None:
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
            client.portfolio.balance(extra_headers={"KALSHI-ACCESS-KEY": "spoofed"})
        assert route.calls[0].request.headers["KALSHI-ACCESS-KEY"] == "test-key-id"


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
