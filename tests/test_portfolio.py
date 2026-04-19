"""Tests for kalshi.resources.portfolio — Portfolio resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiAuthError
from kalshi.resources.portfolio import AsyncPortfolioResource, PortfolioResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def portfolio(test_auth: KalshiAuth, config: KalshiConfig) -> PortfolioResource:
    return PortfolioResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_portfolio(
    test_auth: KalshiAuth, config: KalshiConfig
) -> AsyncPortfolioResource:
    return AsyncPortfolioResource(AsyncTransport(test_auth, config))


# ── Sync tests ──────────────────────────────────────────────


class TestPortfolioBalance:
    @respx.mock
    def test_returns_balance(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 50000,
                    "portfolio_value": 75000,
                    "updated_ts": 1700000000,
                },
            )
        )
        balance = portfolio.balance()
        assert balance.balance == 50000
        assert balance.portfolio_value == 75000
        assert balance.updated_ts == 1700000000

    @respx.mock
    def test_zero_balance(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={"balance": 0, "portfolio_value": 0, "updated_ts": 0},
            )
        )
        balance = portfolio.balance()
        assert balance.balance == 0
        assert balance.portfolio_value == 0

    @respx.mock
    def test_auth_failure(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(401, json={"message": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError):
            portfolio.balance()

    @respx.mock
    def test_balance_with_subaccount(self, portfolio: PortfolioResource) -> None:
        """v0.7.0 ADD: subaccount kwarg reaches the wire."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200, json={"balance": 0, "portfolio_value": 0, "updated_ts": 0}
            )
        )
        portfolio.balance(subaccount=42)
        assert route.calls[0].request.url.params["subaccount"] == "42"


class TestPortfolioPositions:
    @respx.mock
    def test_returns_positions(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [
                        {
                            "ticker": "MKT-A",
                            "total_traded_dollars": "100.0000",
                            "position_fp": "50.00",
                            "market_exposure_dollars": "25.0000",
                            "realized_pnl_dollars": "10.0000",
                            "fees_paid_dollars": "1.5000",
                            "resting_orders_count": 2,
                        }
                    ],
                    "event_positions": [
                        {
                            "event_ticker": "EVT-1",
                            "total_cost_dollars": "200.0000",
                            "total_cost_shares_fp": "100.00",
                            "event_exposure_dollars": "50.0000",
                            "realized_pnl_dollars": "20.0000",
                            "fees_paid_dollars": "3.0000",
                        }
                    ],
                    "cursor": "next-page",
                },
            )
        )
        resp = portfolio.positions()
        assert len(resp.market_positions) == 1
        assert resp.market_positions[0].ticker == "MKT-A"
        assert resp.market_positions[0].total_traded == Decimal("100.0000")
        assert resp.market_positions[0].position == Decimal("50.00")
        assert resp.market_positions[0].market_exposure == Decimal("25.0000")
        assert resp.market_positions[0].realized_pnl == Decimal("10.0000")
        assert resp.market_positions[0].fees_paid == Decimal("1.5000")
        assert len(resp.event_positions) == 1
        assert resp.event_positions[0].event_ticker == "EVT-1"
        assert resp.event_positions[0].total_cost == Decimal("200.0000")
        assert resp.event_positions[0].event_exposure == Decimal("50.0000")
        assert resp.has_next is True
        assert resp.cursor == "next-page"

    @respx.mock
    def test_empty_positions(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [],
                    "event_positions": [],
                },
            )
        )
        resp = portfolio.positions()
        assert resp.market_positions == []
        assert resp.event_positions == []
        assert resp.has_next is False

    @respx.mock
    def test_pagination_cursor(self, portfolio: PortfolioResource) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [],
                    "event_positions": [],
                    "cursor": "",
                },
            )
        )
        resp = portfolio.positions(cursor="abc", limit=10)
        assert route.calls[0].request.url.params["cursor"] == "abc"
        assert route.calls[0].request.url.params["limit"] == "10"
        assert resp.has_next is False  # empty cursor string

    def test_settlement_status_kwarg_removed(self, portfolio: PortfolioResource) -> None:
        """Regression: v0.7.0 dropped phantom settlement_status kwarg.

        It is NOT a valid /portfolio/positions param per spec lines 1055-1090
        (only /fcm/positions has it). NO direct replacement: count_filter is
        a different filter (non-zero numeric fields, not settlement state).
        Migration: filter client-side, OR use /fcm/positions if FCM member.
        """
        with pytest.raises(TypeError, match="settlement_status"):
            portfolio.positions(settlement_status="unsettled")  # type: ignore[call-arg]

    @respx.mock
    def test_positions_with_all_new_filters(self, portfolio: PortfolioResource) -> None:
        """v0.7.0 ADDs: count_filter, ticker, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/positions"
        ).mock(
            return_value=httpx.Response(
                200, json={"market_positions": [], "event_positions": [], "cursor": ""}
            )
        )
        portfolio.positions(
            limit=50,
            cursor="abc",
            count_filter="position",
            ticker="MKT-A",
            event_ticker="EVT-X",
            subaccount=7,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["count_filter"] == "position"
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["subaccount"] == "7"


class TestPortfolioSettlements:
    @respx.mock
    def test_returns_settlements(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(
                200,
                json={
                    "settlements": [
                        {
                            "ticker": "MKT-A",
                            "event_ticker": "EVT-1",
                            "market_result": "yes",
                            "yes_count_fp": "10.00",
                            "yes_total_cost_dollars": "6.5000",
                            "no_count_fp": "0.00",
                            "no_total_cost_dollars": "0.0000",
                            "revenue": 1000,
                            "settled_time": "2026-04-12T12:00:00Z",
                            "fee_cost": "0.3400",
                        }
                    ],
                    "cursor": "page2",
                },
            )
        )
        page = portfolio.settlements()
        assert len(page) == 1
        s = page.items[0]
        assert s.ticker == "MKT-A"
        assert s.market_result == "yes"
        assert s.yes_count == Decimal("10.00")
        assert s.yes_total_cost == Decimal("6.5000")
        assert s.no_count == Decimal("0.00")
        assert s.revenue == 1000
        assert s.fee_cost == Decimal("0.3400")
        assert page.has_next is True

    @respx.mock
    def test_void_settlement(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(
                200,
                json={
                    "settlements": [
                        {
                            "ticker": "MKT-V",
                            "market_result": "void",
                            "yes_count_fp": "5.00",
                            "yes_total_cost_dollars": "3.0000",
                            "no_count_fp": "0.00",
                            "no_total_cost_dollars": "0.0000",
                            "revenue": 300,
                            "settled_time": "2026-04-12T12:00:00Z",
                            "fee_cost": "0.0000",
                        }
                    ],
                    "cursor": "",
                },
            )
        )
        page = portfolio.settlements()
        assert page.items[0].market_result == "void"

    @respx.mock
    def test_empty_settlements(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(200, json={"settlements": []})
        )
        page = portfolio.settlements()
        assert len(page) == 0

    @respx.mock
    def test_settlements_all_paginates(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "settlements": [
                            {
                                "ticker": "A",
                                "market_result": "yes",
                                "yes_count_fp": "1.00",
                                "yes_total_cost_dollars": "0.50",
                                "no_count_fp": "0",
                                "no_total_cost_dollars": "0",
                                "revenue": 100,
                                "settled_time": "2026-04-12T12:00:00Z",
                                "fee_cost": "0.01",
                            }
                        ],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "settlements": [
                            {
                                "ticker": "B",
                                "market_result": "no",
                                "yes_count_fp": "0",
                                "yes_total_cost_dollars": "0",
                                "no_count_fp": "2.00",
                                "no_total_cost_dollars": "1.00",
                                "revenue": 200,
                                "settled_time": "2026-04-12T13:00:00Z",
                                "fee_cost": "0.02",
                            }
                        ],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [s.ticker for s in portfolio.settlements_all()]
        assert tickers == ["A", "B"]

    @respx.mock
    def test_settlements_with_all_new_filters(
        self, portfolio: PortfolioResource
    ) -> None:
        """v0.7.0 ADDs: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/settlements"
        ).mock(return_value=httpx.Response(200, json={"settlements": []}))
        portfolio.settlements(
            ticker="MKT-A",
            event_ticker="EVT-X",
            min_ts=1700000000,
            max_ts=1700099999,
            subaccount=7,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["subaccount"] == "7"

    @respx.mock
    def test_settlements_all_with_all_new_filters(
        self, portfolio: PortfolioResource
    ) -> None:
        """v0.7.0 ADDs on settlements_all match settlements (no cursor)."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/settlements"
        ).mock(
            return_value=httpx.Response(
                200, json={"settlements": [], "cursor": ""}
            )
        )
        list(
            portfolio.settlements_all(
                ticker="MKT-A",
                event_ticker="EVT-X",
                min_ts=1700000000,
                max_ts=1700099999,
                subaccount=7,
            )
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["subaccount"] == "7"


class TestPortfolioTotalRestingOrderValue:
    @respx.mock
    def test_returns_value(self, portfolio: PortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/summary/total_resting_order_value",
        ).mock(
            return_value=httpx.Response(
                200, json={"total_resting_order_value": 12345},
            )
        )
        result = portfolio.total_resting_order_value()
        assert result.total_resting_order_value == 12345

    @respx.mock
    def test_unauthorized(self, portfolio: PortfolioResource) -> None:
        """Demo returns 403 for non-FCM accounts — verify error mapping."""
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/summary/total_resting_order_value",
        ).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        with pytest.raises(KalshiAuthError):
            portfolio.total_resting_order_value()


# ── Async tests ─────────────────────────────────────────────


class TestAsyncPortfolioBalance:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_balance(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={"balance": 50000, "portfolio_value": 75000, "updated_ts": 1700000000},
            )
        )
        balance = await async_portfolio.balance()
        assert balance.balance == 50000
        assert balance.portfolio_value == 75000

    @respx.mock
    @pytest.mark.asyncio
    async def test_balance_with_subaccount(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        """v0.7.0 ADD: subaccount kwarg reaches the wire."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/balance"
        ).mock(
            return_value=httpx.Response(
                200, json={"balance": 0, "portfolio_value": 0, "updated_ts": 0}
            )
        )
        await async_portfolio.balance(subaccount=42)
        assert route.calls[0].request.url.params["subaccount"] == "42"


class TestAsyncPortfolioPositions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_positions(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [
                        {
                            "ticker": "MKT-A",
                            "total_traded_dollars": "100.0000",
                            "position_fp": "50.00",
                            "market_exposure_dollars": "25.0000",
                            "realized_pnl_dollars": "10.0000",
                            "fees_paid_dollars": "1.5000",
                        }
                    ],
                    "event_positions": [],
                    "cursor": "next",
                },
            )
        )
        resp = await async_portfolio.positions()
        assert len(resp.market_positions) == 1
        assert resp.market_positions[0].total_traded == Decimal("100.0000")
        assert resp.has_next is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_positions(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200,
                json={"market_positions": [], "event_positions": []},
            )
        )
        resp = await async_portfolio.positions()
        assert resp.market_positions == []
        assert resp.has_next is False

    @pytest.mark.asyncio
    async def test_settlement_status_kwarg_removed(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        """Regression: v0.7.0 dropped phantom settlement_status kwarg."""
        with pytest.raises(TypeError, match="settlement_status"):
            await async_portfolio.positions(settlement_status="unsettled")  # type: ignore[call-arg]

    @respx.mock
    @pytest.mark.asyncio
    async def test_positions_with_all_new_filters(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        """v0.7.0 ADDs: count_filter, ticker, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/positions"
        ).mock(
            return_value=httpx.Response(
                200, json={"market_positions": [], "event_positions": [], "cursor": ""}
            )
        )
        await async_portfolio.positions(
            limit=50,
            cursor="abc",
            count_filter="position",
            ticker="MKT-A",
            event_ticker="EVT-X",
            subaccount=7,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["count_filter"] == "position"
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["subaccount"] == "7"


class TestAsyncPortfolioSettlements:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_settlements(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(
                200,
                json={
                    "settlements": [
                        {
                            "ticker": "MKT-A",
                            "market_result": "yes",
                            "yes_count_fp": "10.00",
                            "yes_total_cost_dollars": "6.5000",
                            "no_count_fp": "0",
                            "no_total_cost_dollars": "0",
                            "revenue": 1000,
                            "settled_time": "2026-04-12T12:00:00Z",
                            "fee_cost": "0.34",
                        }
                    ],
                    "cursor": "",
                },
            )
        )
        page = await async_portfolio.settlements()
        assert len(page) == 1
        assert page.items[0].yes_count == Decimal("10.00")

    @respx.mock
    @pytest.mark.asyncio
    async def test_settlements_all_paginates(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "settlements": [
                            {
                                "ticker": "A",
                                "market_result": "yes",
                                "yes_count_fp": "1",
                                "yes_total_cost_dollars": "0.5",
                                "no_count_fp": "0",
                                "no_total_cost_dollars": "0",
                                "revenue": 100,
                                "settled_time": "2026-04-12T12:00:00Z",
                                "fee_cost": "0.01",
                            }
                        ],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "settlements": [
                            {
                                "ticker": "B",
                                "market_result": "no",
                                "yes_count_fp": "0",
                                "yes_total_cost_dollars": "0",
                                "no_count_fp": "1",
                                "no_total_cost_dollars": "0.5",
                                "revenue": 100,
                                "settled_time": "2026-04-12T13:00:00Z",
                                "fee_cost": "0.01",
                            }
                        ],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [s.ticker async for s in async_portfolio.settlements_all()]
        assert tickers == ["A", "B"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_settlements_with_all_new_filters(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        """v0.7.0 ADDs: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/settlements"
        ).mock(return_value=httpx.Response(200, json={"settlements": []}))
        await async_portfolio.settlements(
            ticker="MKT-A",
            event_ticker="EVT-X",
            min_ts=1700000000,
            max_ts=1700099999,
            subaccount=7,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["subaccount"] == "7"

    @respx.mock
    @pytest.mark.asyncio
    async def test_settlements_all_with_all_new_filters(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        """v0.7.0 ADDs on settlements_all match settlements (no cursor)."""
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/settlements"
        ).mock(
            return_value=httpx.Response(
                200, json={"settlements": [], "cursor": ""}
            )
        )
        _ = [s async for s in async_portfolio.settlements_all(
            ticker="MKT-A",
            event_ticker="EVT-X",
            min_ts=1700000000,
            max_ts=1700099999,
            subaccount=7,
        )]
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["subaccount"] == "7"


class TestAsyncPortfolioTotalRestingOrderValue:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_value(
        self, async_portfolio: AsyncPortfolioResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/summary/total_resting_order_value",
        ).mock(
            return_value=httpx.Response(
                200, json={"total_resting_order_value": 99999},
            )
        )
        result = await async_portfolio.total_resting_order_value()
        assert result.total_resting_order_value == 99999
