"""Tests for the perps portfolio resource — positions, fills, trades (#393)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import (
    AuthRequiredError,
    KalshiAuthError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.portfolio import MarginFill, MarginPosition, MarginTrade

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


# ── sample payloads ──────────────────────────────────────────────────────────


def _long_position() -> dict[str, object]:
    return {
        "subaccount": 0,
        "market_ticker": "BTC-PERP",
        "position": "100.00",
        "entry_price": "0.5600",
        "unrealized_pnl": "12.3400",
        "margin_used": "50.0000",
        "fees": "1.2500",
        "roe": 24.68,
        "is_portfolio": False,
    }


def _short_position() -> dict[str, object]:
    return {
        "subaccount": 1,
        "market_ticker": "ETH-PERP",
        "position": "-40.00",
        "entry_price": "0.3300",
        "unrealized_pnl": "-5.5000",
        "margin_used": "20.0000",
        "fees": "0.8000",
        "roe": -27.5,
        "is_portfolio": True,
    }


def _fill(order_source: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "fill_id": "f-1",
        "order_id": "o-1",
        "is_taker": True,
        "side": "bid",
        "count": "10.00",
        "created_time": "2026-06-04T12:00:00Z",
        "ticker": "BTC-PERP",
        "price": "0.5600",
        "entry_price": "0.5500",
        "fees": "0.1000",
        "realized_pnl": "-2.5000",
    }
    if order_source is not None:
        payload["order_source"] = order_source
    return payload


def _trade() -> dict[str, object]:
    return {
        "trade_id": "t-1",
        "ticker": "BTC-PERP",
        "count": "5.00",
        "price": "0.5700",
        "created_time": "2026-06-04T12:00:01Z",
        "taker_side": "ask",
    }


# ── positions ────────────────────────────────────────────────────────────────


class TestPositions:
    @respx.mock
    def test_happy_long_and_short(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(
                200, json={"positions": [_long_position(), _short_position()]}
            )
        )
        resp = perps_client.portfolio.positions()
        assert len(resp.positions) == 2
        long, short = resp.positions
        assert isinstance(long, MarginPosition)
        assert isinstance(long.entry_price, Decimal)
        assert isinstance(long.margin_used, Decimal)
        assert isinstance(long.fees, Decimal)
        assert long.position == Decimal("100.00")
        assert short.position == Decimal("-40.00")
        assert short.unrealized_pnl == Decimal("-5.5000")
        # roe wire name surfaces as return_on_equity (MultiplierDecimal).
        assert long.return_on_equity == Decimal("24.68")
        assert isinstance(long.return_on_equity, Decimal)
        assert short.return_on_equity == Decimal("-27.5")
        assert route.called

    @respx.mock
    def test_roe_null(self, perps_client: PerpsClient) -> None:
        payload = _long_position()
        payload["roe"] = None
        respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": [payload]})
        )
        resp = perps_client.portfolio.positions()
        assert resp.positions[0].return_on_equity is None

    def test_position_requires_is_portfolio(self) -> None:
        # is_portfolio is spec-required (v3.23.0); a 3.23.0 server always sends
        # it, so omitting it is a hard error rather than a silent default.
        payload = _long_position()
        del payload["is_portfolio"]
        with pytest.raises(ValidationError):
            MarginPosition.model_validate(payload)

    @respx.mock
    def test_empty_positions(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": []})
        )
        assert perps_client.portfolio.positions().positions == []

    @respx.mock
    def test_null_positions_coerced_to_empty(self, perps_client: PerpsClient) -> None:
        # NullableList tolerates server null and coerces to [].
        respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": None})
        )
        assert perps_client.portfolio.positions().positions == []

    @respx.mock
    def test_query_params_dropped_when_none(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": []})
        )
        perps_client.portfolio.positions(subaccount=3, ticker="BTC-PERP")
        request = route.calls.last.request
        assert request.url.params["subaccount"] == "3"
        assert request.url.params["ticker"] == "BTC-PERP"

    @respx.mock
    def test_query_params_omitted(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": []})
        )
        perps_client.portfolio.positions()
        request = route.calls.last.request
        assert "subaccount" not in request.url.params
        assert "ticker" not in request.url.params

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": []})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.portfolio.positions()
        assert not route.called
        client.close()

    @respx.mock
    def test_server_401_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(KalshiAuthError):
            perps_client.portfolio.positions()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": [_long_position()]})
        )
        resp = await async_perps_client.portfolio.positions()
        assert resp.positions[0].position == Decimal("100.00")
        await async_perps_client.close()

    @respx.mock
    async def test_async_unauth_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/positions").mock(
            return_value=httpx.Response(200, json={"positions": []})
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            await client.portfolio.positions()
        assert not route.called
        await client.close()


# ── fills / fills_all ────────────────────────────────────────────────────────


class TestFills:
    @respx.mock
    def test_happy_single_page(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [_fill()], "cursor": ""})
        )
        page = perps_client.portfolio.fills()
        assert len(page.items) == 1
        fill = page.items[0]
        assert isinstance(fill, MarginFill)
        assert fill.side == "bid"
        assert isinstance(fill.created_time, datetime)
        assert fill.created_time.tzinfo is not None
        assert fill.realized_pnl == Decimal("-2.5000")
        assert page.has_next is False
        assert route.called

    @respx.mock
    def test_order_source_present_and_absent(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(
                200,
                json={"fills": [_fill("system"), _fill()], "cursor": ""},
            )
        )
        fills = perps_client.portfolio.fills().items
        assert fills[0].order_source == "system"
        assert fills[1].order_source is None

    @respx.mock
    def test_query_params(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [], "cursor": ""})
        )
        perps_client.portfolio.fills(
            subaccount=2, min_ts=1000, max_ts=2000, limit=50, cursor="c0"
        )
        params = route.calls.last.request.url.params
        assert params["subaccount"] == "2"
        assert params["min_ts"] == "1000"
        assert params["max_ts"] == "2000"
        assert params["limit"] == "50"
        assert params["cursor"] == "c0"

    @respx.mock
    def test_params_dropped_when_none(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [], "cursor": ""})
        )
        perps_client.portfolio.fills()
        params = route.calls.last.request.url.params
        for key in ("subaccount", "min_ts", "max_ts", "limit", "cursor"):
            assert key not in params

    def test_limit_out_of_range_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValueError):
            perps_client.portfolio.fills(limit=1001)

    @respx.mock
    def test_fills_all_paginates(self, perps_client: PerpsClient) -> None:
        responses = [
            httpx.Response(200, json={"fills": [_fill(), _fill()], "cursor": "abc"}),
            httpx.Response(200, json={"fills": [_fill()], "cursor": ""}),
        ]
        respx.get(f"{BASE}/margin/fills").mock(side_effect=responses)
        items = list(perps_client.portfolio.fills_all())
        assert len(items) == 3
        assert all(isinstance(f, MarginFill) for f in items)

    @respx.mock
    def test_fills_all_max_pages_cap(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [_fill()], "cursor": "more"})
        )
        items = list(perps_client.portfolio.fills_all(max_pages=1))
        assert len(items) == 1
        assert route.call_count == 1

    def test_fills_all_invalid_max_pages_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValueError):
            list(perps_client.portfolio.fills_all(max_pages=0))

    @respx.mock
    def test_server_500_propagates(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/fills").mock(return_value=httpx.Response(500))
        with pytest.raises(KalshiServerError):
            perps_client.portfolio.fills()

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [], "cursor": ""})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.portfolio.fills()
        assert not route.called
        client.close()

    @respx.mock
    def test_fills_all_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [], "cursor": ""})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            list(client.portfolio.fills_all())
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [_fill()], "cursor": ""})
        )
        page = await async_perps_client.portfolio.fills()
        assert page.items[0].side == "bid"
        await async_perps_client.close()

    @respx.mock
    async def test_async_fills_all_paginates(
        self, async_perps_client: AsyncPerpsClient
    ) -> None:
        responses = [
            httpx.Response(200, json={"fills": [_fill(), _fill()], "cursor": "abc"}),
            httpx.Response(200, json={"fills": [_fill()], "cursor": ""}),
        ]
        respx.get(f"{BASE}/margin/fills").mock(side_effect=responses)
        items = [f async for f in async_perps_client.portfolio.fills_all()]
        assert len(items) == 3
        await async_perps_client.close()

    @respx.mock
    async def test_async_fills_all_unauth_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/fills").mock(
            return_value=httpx.Response(200, json={"fills": [], "cursor": ""})
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            # fills_all is a plain def returning an AsyncIterator — the auth
            # check fires before any HTTP, at call time (not on first iteration).
            client.portfolio.fills_all()
        assert not route.called
        await client.close()


# ── trades / trades_all ──────────────────────────────────────────────────────


class TestTrades:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/trades").mock(
            return_value=httpx.Response(200, json={"trades": [_trade()], "cursor": ""})
        )
        page = perps_client.portfolio.trades(ticker="BTC-PERP")
        assert len(page.items) == 1
        trade = page.items[0]
        assert isinstance(trade, MarginTrade)
        assert trade.taker_side == "ask"
        assert isinstance(trade.price, Decimal)
        assert trade.count == Decimal("5.00")
        assert isinstance(trade.created_time, datetime)
        assert page.has_next is False
        # ticker always present on /margin/trades.
        assert route.calls.last.request.url.params["ticker"] == "BTC-PERP"

    @respx.mock
    def test_public_unauthenticated_client_works(self) -> None:
        # /margin/trades is public — no _require_auth(), so an unauth client works.
        route = respx.get(f"{BASE}/margin/trades").mock(
            return_value=httpx.Response(200, json={"trades": [_trade()], "cursor": ""})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        page = client.portfolio.trades(ticker="BTC-PERP")
        assert len(page.items) == 1
        assert route.called
        client.close()

    def test_ticker_required(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.portfolio.trades()  # type: ignore[call-arg]

    def test_trades_all_ticker_required(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            list(perps_client.portfolio.trades_all())  # type: ignore[call-arg]

    @respx.mock
    def test_query_params(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/trades").mock(
            return_value=httpx.Response(200, json={"trades": [], "cursor": ""})
        )
        perps_client.portfolio.trades(
            ticker="ETH-PERP", min_ts=10, max_ts=20, limit=25, cursor="x"
        )
        params = route.calls.last.request.url.params
        assert params["ticker"] == "ETH-PERP"
        assert params["min_ts"] == "10"
        assert params["max_ts"] == "20"
        assert params["limit"] == "25"
        assert params["cursor"] == "x"

    @respx.mock
    def test_optional_params_dropped(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/trades").mock(
            return_value=httpx.Response(200, json={"trades": [], "cursor": ""})
        )
        perps_client.portfolio.trades(ticker="BTC-PERP")
        params = route.calls.last.request.url.params
        assert params["ticker"] == "BTC-PERP"
        for key in ("min_ts", "max_ts", "limit", "cursor"):
            assert key not in params

    def test_limit_out_of_range_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValueError):
            perps_client.portfolio.trades(ticker="BTC-PERP", limit=0)

    @respx.mock
    def test_trades_all_paginates(self, perps_client: PerpsClient) -> None:
        responses = [
            httpx.Response(200, json={"trades": [_trade(), _trade()], "cursor": "p2"}),
            httpx.Response(200, json={"trades": [_trade()], "cursor": ""}),
        ]
        respx.get(f"{BASE}/margin/trades").mock(side_effect=responses)
        items = list(perps_client.portfolio.trades_all(ticker="BTC-PERP"))
        assert len(items) == 3

    @respx.mock
    def test_trades_all_max_pages_cap(self, perps_client: PerpsClient) -> None:
        # Distinct cursors per page so the cursor-loop guard doesn't trip; the
        # cap stops iteration before the (never-empty) third page is fetched.
        responses = [
            httpx.Response(200, json={"trades": [_trade()], "cursor": "p2"}),
            httpx.Response(200, json={"trades": [_trade()], "cursor": "p3"}),
            httpx.Response(200, json={"trades": [_trade()], "cursor": "p4"}),
        ]
        route = respx.get(f"{BASE}/margin/trades").mock(side_effect=responses)
        items = list(perps_client.portfolio.trades_all(ticker="BTC-PERP", max_pages=2))
        assert len(items) == 2
        assert route.call_count == 2

    @respx.mock
    def test_bad_request_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/trades").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_ticker"}})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.portfolio.trades(ticker="NOPE")

    @respx.mock
    async def test_async_public_unauthenticated_works(self) -> None:
        route = respx.get(f"{BASE}/margin/trades").mock(
            return_value=httpx.Response(200, json={"trades": [_trade()], "cursor": ""})
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        page = await client.portfolio.trades(ticker="BTC-PERP")
        assert page.items[0].taker_side == "ask"
        assert route.called
        await client.close()

    @respx.mock
    async def test_async_trades_all_paginates(
        self, async_perps_client: AsyncPerpsClient
    ) -> None:
        responses = [
            httpx.Response(200, json={"trades": [_trade()], "cursor": "p2"}),
            httpx.Response(200, json={"trades": [_trade()], "cursor": ""}),
        ]
        respx.get(f"{BASE}/margin/trades").mock(side_effect=responses)
        items = [t async for t in async_perps_client.portfolio.trades_all(ticker="BTC-PERP")]
        assert len(items) == 2
        await async_perps_client.close()
