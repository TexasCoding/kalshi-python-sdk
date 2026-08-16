"""Tests for kalshi.resources.portfolio — Portfolio resource."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import AuthRequiredError, KalshiAuthError
from kalshi.resources.portfolio import AsyncPortfolioResource, PortfolioResource
from tests._model_fixtures import (
    event_position_dict,
    fill_dict,
    market_position_dict,
    settlement_dict,
)


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
def async_portfolio(test_auth: KalshiAuth, config: KalshiConfig) -> AsyncPortfolioResource:
    return AsyncPortfolioResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_portfolio(config: KalshiConfig) -> PortfolioResource:
    return PortfolioResource(SyncTransport(None, config))


@pytest.fixture
def unauth_async_portfolio(config: KalshiConfig) -> AsyncPortfolioResource:
    return AsyncPortfolioResource(AsyncTransport(None, config))


# ── Sync tests ──────────────────────────────────────────────


class TestPortfolioBalance:
    @respx.mock
    def test_returns_balance(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 50000,
                    "balance_dollars": "500.00",
                    "portfolio_value": 75000,
                    "updated_ts": 1700000000,
                },
            )
        )
        balance = portfolio.balance()
        assert balance.balance == 50000
        assert balance.balance_dollars == Decimal("500.00")
        assert balance.portfolio_value == 75000
        assert balance.updated_ts == 1700000000

    @respx.mock
    def test_zero_balance(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 0,
                    "balance_dollars": "0.00",
                    "portfolio_value": 0,
                    "updated_ts": 0,
                },
            )
        )
        balance = portfolio.balance()
        assert balance.balance == 0
        assert balance.balance_dollars == Decimal("0.00")
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
                200,
                json={
                    "balance": 0,
                    "balance_dollars": "0.00",
                    "portfolio_value": 0,
                    "updated_ts": 0,
                },
            )
        )
        portfolio.balance(subaccount=42)
        assert route.calls[0].request.url.params["subaccount"] == "42"

    @respx.mock
    def test_balance_breakdown(self, portfolio: PortfolioResource) -> None:
        """Spec v3.18.0 adds balance_breakdown — optional per-shard split."""
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 50000,
                    "balance_dollars": "500.00",
                    "portfolio_value": 75000,
                    "updated_ts": 1700000000,
                    "balance_breakdown": [
                        {"exchange_index": 0, "balance": "500.00"},
                    ],
                },
            )
        )
        balance = portfolio.balance()
        assert balance.balance_breakdown is not None
        assert len(balance.balance_breakdown) == 1
        assert balance.balance_breakdown[0].exchange_index == 0
        assert balance.balance_breakdown[0].balance == Decimal("500.00")

    @respx.mock
    def test_balance_breakdown_omitted(self, portfolio: PortfolioResource) -> None:
        """balance_breakdown is optional — must default to None when absent."""
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 50000,
                    "balance_dollars": "500.00",
                    "portfolio_value": 75000,
                    "updated_ts": 1700000000,
                },
            )
        )
        balance = portfolio.balance()
        assert balance.balance_breakdown is None


class TestPortfolioPositions:
    @respx.mock
    def test_returns_positions(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [
                        market_position_dict(
                            ticker="MKT-A",
                            total_traded_dollars="100.0000",
                            position_fp="50.00",
                            market_exposure_dollars="25.0000",
                            realized_pnl_dollars="10.0000",
                            fees_paid_dollars="1.5000",
                            resting_orders_count=2,
                        )
                    ],
                    "event_positions": [
                        event_position_dict(
                            event_ticker="EVT-1",
                            total_cost_dollars="200.0000",
                            total_cost_shares_fp="100.00",
                            event_exposure_dollars="50.0000",
                            realized_pnl_dollars="20.0000",
                            fees_paid_dollars="3.0000",
                        )
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
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
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
            exchange_index=0,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["count_filter"] == "position"
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["subaccount"] == "7"
        assert params["exchange_index"] == "0"


class TestPortfolioPositionsAll:
    @respx.mock
    def test_positions_all_paginates(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "market_positions": [
                            market_position_dict(ticker="A"),
                            market_position_dict(ticker="B"),
                        ],
                        "event_positions": [],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="C")],
                        "event_positions": [],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [p.ticker for p in portfolio.positions_all()]
        assert tickers == ["A", "B", "C"]

    @respx.mock
    def test_positions_all_forwards_filters_and_omits_cursor(
        self, portfolio: PortfolioResource
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200, json={"market_positions": [], "event_positions": [], "cursor": ""}
            )
        )
        list(
            portfolio.positions_all(
                limit=100,
                count_filter="position",
                ticker="MKT-A",
                event_ticker="EVT-X",
                subaccount=3,
                exchange_index=1,
            )
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "100"
        assert params["count_filter"] == "position"
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["subaccount"] == "3"
        assert params["exchange_index"] == "1"
        assert "cursor" not in params

    def test_positions_all_requires_auth(self, unauth_portfolio: PortfolioResource) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_portfolio.positions_all())

    def test_positions_all_rejects_zero_max_pages(self, portfolio: PortfolioResource) -> None:
        with pytest.raises(ValueError, match="max_pages must be positive"):
            list(portfolio.positions_all(max_pages=0))


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
                        settlement_dict(
                            ticker="MKT-V",
                            market_result="void",
                            yes_count_fp="5.00",
                            yes_total_cost_dollars="3.0000",
                            no_count_fp="0.00",
                            no_total_cost_dollars="0.0000",
                            revenue=300,
                            settled_time="2026-04-12T12:00:00Z",
                            fee_cost="0.0000",
                        )
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
                            settlement_dict(
                                ticker="A",
                                market_result="yes",
                                yes_count_fp="1.00",
                                yes_total_cost_dollars="0.50",
                                no_count_fp="0",
                                no_total_cost_dollars="0",
                                revenue=100,
                                settled_time="2026-04-12T12:00:00Z",
                                fee_cost="0.01",
                            )
                        ],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "settlements": [
                            settlement_dict(
                                ticker="B",
                                market_result="no",
                                yes_count_fp="0",
                                yes_total_cost_dollars="0",
                                no_count_fp="2.00",
                                no_total_cost_dollars="1.00",
                                revenue=200,
                                settled_time="2026-04-12T13:00:00Z",
                                fee_cost="0.02",
                            )
                        ],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [s.ticker for s in portfolio.settlements_all()]
        assert tickers == ["A", "B"]

    @respx.mock
    def test_settlements_with_all_new_filters(self, portfolio: PortfolioResource) -> None:
        """v0.7.0 ADDs: event_ticker, min_ts, max_ts, subaccount."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(200, json={"settlements": []})
        )
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
    def test_settlements_all_with_all_new_filters(self, portfolio: PortfolioResource) -> None:
        """v0.7.0 ADDs on settlements_all match settlements (no cursor)."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(200, json={"settlements": [], "cursor": ""})
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
                200,
                json={
                    "total_resting_order_value": 12345,
                    "resting_order_value_breakdown": [
                        {"exchange_index": 0, "balance": "123.4500"},
                    ],
                },
            )
        )
        result = portfolio.total_resting_order_value()
        assert result.total_resting_order_value == 12345
        assert len(result.resting_order_value_breakdown) == 1
        assert result.resting_order_value_breakdown[0].exchange_index == 0
        assert result.resting_order_value_breakdown[0].balance == Decimal("123.4500")

    @respx.mock
    def test_unauthorized(self, portfolio: PortfolioResource) -> None:
        """Demo returns 403 for non-FCM accounts — verify error mapping."""
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/summary/total_resting_order_value",
        ).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        with pytest.raises(KalshiAuthError):
            portfolio.total_resting_order_value()


_DEPOSIT = {
    "id": "dep_1",
    "status": "applied",
    "type": "ach",
    "amount_cents": 10000,
    "fee_cents": 0,
    "created_ts": 1700000000,
    "finalized_ts": 1700001000,
}

_WITHDRAWAL = {
    "id": "wd_1",
    "status": "pending",
    "type": "wire",
    "amount_cents": 5000,
    "fee_cents": 25,
    "created_ts": 1700000000,
    "finalized_ts": None,
}


class TestPortfolioDeposits:
    @respx.mock
    def test_returns_page(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/deposits").mock(
            return_value=httpx.Response(
                200,
                json={"deposits": [_DEPOSIT], "cursor": "abc"},
            )
        )
        page = portfolio.deposits(limit=10)
        assert len(page.items) == 1
        assert page.items[0].id == "dep_1"
        assert page.items[0].status == "applied"
        assert page.cursor == "abc"

    @respx.mock
    def test_empty(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/deposits").mock(
            return_value=httpx.Response(200, json={"deposits": []})
        )
        page = portfolio.deposits()
        assert page.items == []
        assert page.cursor is None

    @respx.mock
    def test_all_paginates(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/deposits").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "deposits": [_DEPOSIT, {**_DEPOSIT, "id": "dep_2"}],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={"deposits": [{**_DEPOSIT, "id": "dep_3"}], "cursor": ""},
                ),
            ]
        )
        items = list(portfolio.deposits_all(limit=2))
        assert [d.id for d in items] == ["dep_1", "dep_2", "dep_3"]

    @respx.mock
    def test_all_max_pages_caps(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/deposits").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"deposits": [_DEPOSIT], "cursor": "p2"},
                ),
                httpx.Response(
                    200,
                    json={"deposits": [{**_DEPOSIT, "id": "dep_2"}], "cursor": "p3"},
                ),
            ]
        )
        items = list(portfolio.deposits_all(max_pages=2))
        # max_pages=2 stops after 2 pages even though cursor "p3" is non-empty.
        assert len(items) == 2

    @respx.mock
    def test_auth_failure(self, portfolio: PortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/deposits").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError):
            portfolio.deposits()

    def test_deposits_requires_auth(
        self,
        unauth_portfolio: PortfolioResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_portfolio.deposits()

    def test_deposits_all_requires_auth(
        self,
        unauth_portfolio: PortfolioResource,
    ) -> None:
        # *_all returns an iterator — must raise eagerly, not on first iteration.
        with pytest.raises(AuthRequiredError):
            unauth_portfolio.deposits_all()


class TestPortfolioWithdrawals:
    @respx.mock
    def test_returns_page(self, portfolio: PortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/withdrawals",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"withdrawals": [_WITHDRAWAL], "cursor": None},
            )
        )
        page = portfolio.withdrawals()
        assert len(page.items) == 1
        assert page.items[0].id == "wd_1"
        assert page.items[0].fee_cents == 25
        assert page.items[0].finalized_ts is None
        assert page.cursor is None

    @respx.mock
    def test_all_paginates(self, portfolio: PortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/withdrawals",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"withdrawals": [_WITHDRAWAL], "cursor": "p2"},
                ),
                httpx.Response(
                    200,
                    json={"withdrawals": [{**_WITHDRAWAL, "id": "wd_2"}], "cursor": ""},
                ),
            ]
        )
        items = list(portfolio.withdrawals_all())
        assert [w.id for w in items] == ["wd_1", "wd_2"]

    @respx.mock
    def test_auth_failure(self, portfolio: PortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/withdrawals",
        ).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        with pytest.raises(KalshiAuthError):
            portfolio.withdrawals()

    def test_withdrawals_requires_auth(
        self,
        unauth_portfolio: PortfolioResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_portfolio.withdrawals()

    def test_withdrawals_all_requires_auth(
        self,
        unauth_portfolio: PortfolioResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_portfolio.withdrawals_all()


# ── Async tests ─────────────────────────────────────────────


class TestAsyncPortfolioBalance:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_balance(self, async_portfolio: AsyncPortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 50000,
                    "balance_dollars": "500.00",
                    "portfolio_value": 75000,
                    "updated_ts": 1700000000,
                },
            )
        )
        balance = await async_portfolio.balance()
        assert balance.balance == 50000
        assert balance.balance_dollars == Decimal("500.00")
        assert balance.portfolio_value == 75000

    @respx.mock
    @pytest.mark.asyncio
    async def test_balance_with_subaccount(self, async_portfolio: AsyncPortfolioResource) -> None:
        """v0.7.0 ADD: subaccount kwarg reaches the wire."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "balance": 0,
                    "balance_dollars": "0.00",
                    "portfolio_value": 0,
                    "updated_ts": 0,
                },
            )
        )
        await async_portfolio.balance(subaccount=42)
        assert route.calls[0].request.url.params["subaccount"] == "42"


class TestAsyncPortfolioPositions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_positions(self, async_portfolio: AsyncPortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_positions": [
                        market_position_dict(
                            ticker="MKT-A",
                            total_traded_dollars="100.0000",
                            position_fp="50.00",
                            market_exposure_dollars="25.0000",
                            realized_pnl_dollars="10.0000",
                            fees_paid_dollars="1.5000",
                        )
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
    async def test_empty_positions(self, async_portfolio: AsyncPortfolioResource) -> None:
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
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
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
            exchange_index=0,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["count_filter"] == "position"
        assert params["ticker"] == "MKT-A"
        assert params["event_ticker"] == "EVT-X"
        assert params["subaccount"] == "7"
        assert params["exchange_index"] == "0"


class TestAsyncPortfolioSettlements:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_settlements(self, async_portfolio: AsyncPortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(
                200,
                json={
                    "settlements": [
                        settlement_dict(
                            ticker="MKT-A",
                            market_result="yes",
                            yes_count_fp="10.00",
                            yes_total_cost_dollars="6.5000",
                            no_count_fp="0",
                            no_total_cost_dollars="0",
                            revenue=1000,
                            settled_time="2026-04-12T12:00:00Z",
                            fee_cost="0.34",
                        )
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
    async def test_settlements_all_paginates(self, async_portfolio: AsyncPortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "settlements": [
                            settlement_dict(
                                ticker="A",
                                market_result="yes",
                                yes_count_fp="1",
                                yes_total_cost_dollars="0.5",
                                no_count_fp="0",
                                no_total_cost_dollars="0",
                                revenue=100,
                                settled_time="2026-04-12T12:00:00Z",
                                fee_cost="0.01",
                            )
                        ],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "settlements": [
                            settlement_dict(
                                ticker="B",
                                market_result="no",
                                yes_count_fp="0",
                                yes_total_cost_dollars="0",
                                no_count_fp="1",
                                no_total_cost_dollars="0.5",
                                revenue=100,
                                settled_time="2026-04-12T13:00:00Z",
                                fee_cost="0.01",
                            )
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
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(200, json={"settlements": []})
        )
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
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/settlements").mock(
            return_value=httpx.Response(200, json={"settlements": [], "cursor": ""})
        )
        _ = [
            s
            async for s in async_portfolio.settlements_all(
                ticker="MKT-A",
                event_ticker="EVT-X",
                min_ts=1700000000,
                max_ts=1700099999,
                subaccount=7,
            )
        ]
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
        self,
        async_portfolio: AsyncPortfolioResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/summary/total_resting_order_value",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_resting_order_value": 99999,
                    "resting_order_value_breakdown": [],
                },
            )
        )
        result = await async_portfolio.total_resting_order_value()
        assert result.total_resting_order_value == 99999

    @respx.mock
    @pytest.mark.asyncio
    async def test_unauthorized(
        self,
        async_portfolio: AsyncPortfolioResource,
    ) -> None:
        """Demo returns 401/403 for non-FCM accounts — verify error mapping."""
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/summary/total_resting_order_value",
        ).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        with pytest.raises(KalshiAuthError):
            await async_portfolio.total_resting_order_value()


class TestAsyncPortfolioDeposits:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(
        self,
        async_portfolio: AsyncPortfolioResource,
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/deposits").mock(
            return_value=httpx.Response(
                200,
                json={"deposits": [_DEPOSIT], "cursor": None},
            )
        )
        page = await async_portfolio.deposits()
        assert page.items[0].id == "dep_1"
        assert page.cursor is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_all_paginates(
        self,
        async_portfolio: AsyncPortfolioResource,
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/deposits").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"deposits": [_DEPOSIT], "cursor": "p2"},
                ),
                httpx.Response(
                    200,
                    json={"deposits": [{**_DEPOSIT, "id": "dep_2"}], "cursor": ""},
                ),
            ]
        )
        items = [d async for d in async_portfolio.deposits_all()]
        assert [d.id for d in items] == ["dep_1", "dep_2"]


class TestAsyncPortfolioWithdrawals:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(
        self,
        async_portfolio: AsyncPortfolioResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/withdrawals",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"withdrawals": [_WITHDRAWAL]},
            )
        )
        page = await async_portfolio.withdrawals()
        assert page.items[0].id == "wd_1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_all_max_pages_caps(
        self,
        async_portfolio: AsyncPortfolioResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/withdrawals",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"withdrawals": [_WITHDRAWAL], "cursor": "p2"},
                ),
                httpx.Response(
                    200,
                    json={
                        "withdrawals": [{**_WITHDRAWAL, "id": "wd_2"}],
                        "cursor": "p3",
                    },
                ),
            ]
        )
        items = [w async for w in async_portfolio.withdrawals_all(max_pages=2)]
        assert len(items) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_auth_failure(
        self,
        async_portfolio: AsyncPortfolioResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/withdrawals",
        ).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        with pytest.raises(KalshiAuthError):
            await async_portfolio.withdrawals()

    @pytest.mark.asyncio
    async def test_withdrawals_requires_auth(
        self,
        unauth_async_portfolio: AsyncPortfolioResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_portfolio.withdrawals()

    def test_withdrawals_all_requires_auth(
        self,
        unauth_async_portfolio: AsyncPortfolioResource,
    ) -> None:
        # withdrawals_all is plain `def` returning AsyncIterator; auth check
        # must fire at call time, not on first iteration.
        with pytest.raises(AuthRequiredError):
            unauth_async_portfolio.withdrawals_all()


class TestAsyncPortfolioDepositsAuth:
    @pytest.mark.asyncio
    async def test_deposits_requires_auth(
        self,
        unauth_async_portfolio: AsyncPortfolioResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_portfolio.deposits()

    def test_deposits_all_requires_auth(
        self,
        unauth_async_portfolio: AsyncPortfolioResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_async_portfolio.deposits_all()


class TestAsyncPortfolioPositionsAll:
    @pytest.mark.asyncio
    @respx.mock
    async def test_positions_all_paginates(self, async_portfolio: AsyncPortfolioResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/positions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="A")],
                        "event_positions": [],
                        "cursor": "page2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "market_positions": [market_position_dict(ticker="B")],
                        "event_positions": [],
                        "cursor": "",
                    },
                ),
            ]
        )
        tickers = [p.ticker async for p in async_portfolio.positions_all()]
        assert tickers == ["A", "B"]

    @pytest.mark.asyncio
    async def test_positions_all_requires_auth(
        self, unauth_async_portfolio: AsyncPortfolioResource
    ) -> None:
        with pytest.raises(AuthRequiredError):
            async for _ in unauth_async_portfolio.positions_all():
                pass


# ── Issue #351: fills moved from OrdersResource to PortfolioResource ─────────


class TestPortfolioFills:
    @respx.mock
    def test_issue_351_fills_on_portfolio_resource_works(
        self, portfolio: PortfolioResource
    ) -> None:
        """New location: client.portfolio.fills() hits /portfolio/fills and parses Page[Fill]."""
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        fill_dict(
                            trade_id="t1", order_id="o1", yes_price_dollars="0.5000", count_fp="5"
                        )
                    ],
                    "cursor": "",
                },
            )
        )
        page = portfolio.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"
        assert page.items[0].yes_price == Decimal("0.5000")

    @respx.mock
    def test_fills_cursor_and_filter_parity(self, portfolio: PortfolioResource) -> None:
        """ticker / min_ts / max_ts / cursor reach the wire identically to old shape."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        portfolio.fills(
            ticker="MKT-A",
            order_id="ord-1",
            min_ts=1700000000,
            max_ts=1700099999,
            limit=50,
            cursor="abc",
            subaccount=7,
            exchange_index=0,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["subaccount"] == "7"
        assert params["exchange_index"] == "0"

    def test_fills_requires_auth(self, unauth_portfolio: PortfolioResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_portfolio.fills()


class TestPortfolioFillsAll:
    @respx.mock
    def test_issue_351_fills_all_on_portfolio_resource_works(
        self, portfolio: PortfolioResource
    ) -> None:
        """New location: client.portfolio.fills_all() auto-paginates."""
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "fills": [fill_dict(trade_id="a", yes_price_dollars="0.50")],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "fills": [fill_dict(trade_id="b", yes_price_dollars="0.60")],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [f.trade_id for f in portfolio.fills_all()]
        assert ids == ["a", "b"]

    def test_fills_all_requires_auth(self, unauth_portfolio: PortfolioResource) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_portfolio.fills_all())


class TestAsyncPortfolioFills:
    @respx.mock
    @pytest.mark.asyncio
    async def test_issue_351_fills_on_portfolio_resource_works(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fills": [
                        fill_dict(
                            trade_id="t1", order_id="o1", yes_price_dollars="0.5000", count_fp="5"
                        )
                    ],
                    "cursor": "",
                },
            )
        )
        page = await async_portfolio.fills()
        assert len(page) == 1
        assert page.items[0].trade_id == "t1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fills_cursor_and_filter_parity(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        await async_portfolio.fills(
            ticker="MKT-A",
            order_id="ord-1",
            min_ts=1700000000,
            max_ts=1700099999,
            limit=50,
            cursor="abc",
            subaccount=7,
            exchange_index=0,
        )
        params = dict(route.calls[0].request.url.params)
        assert params["ticker"] == "MKT-A"
        assert params["order_id"] == "ord-1"
        assert params["min_ts"] == "1700000000"
        assert params["max_ts"] == "1700099999"
        assert params["limit"] == "50"
        assert params["cursor"] == "abc"
        assert params["subaccount"] == "7"
        assert params["exchange_index"] == "0"

    @pytest.mark.asyncio
    async def test_fills_requires_auth(
        self, unauth_async_portfolio: AsyncPortfolioResource
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_portfolio.fills()


class TestAsyncPortfolioFillsAll:
    @respx.mock
    @pytest.mark.asyncio
    async def test_issue_351_fills_all_on_portfolio_resource_works(
        self, async_portfolio: AsyncPortfolioResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/portfolio/fills").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "fills": [fill_dict(trade_id="a", yes_price_dollars="0.50")],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "fills": [fill_dict(trade_id="b", yes_price_dollars="0.60")],
                        "cursor": "",
                    },
                ),
            ]
        )
        ids = [f.trade_id async for f in async_portfolio.fills_all()]
        assert ids == ["a", "b"]

    @pytest.mark.asyncio
    async def test_fills_all_requires_auth(
        self, unauth_async_portfolio: AsyncPortfolioResource
    ) -> None:
        with pytest.raises(AuthRequiredError):
            async for _ in unauth_async_portfolio.fills_all():
                pass


# ── Intra-exchange instance transfers (#496/#497) ───────────────────────


_TRANSFER = {
    "transfer_id": "xfer-1",
    "source": "event_contract",
    "destination": "margined",
    "source_exchange_shard": 0,
    "destination_exchange_shard": 0,
    "amount": "25.5000",
    "status": "complete",
    "created_ts": 1_700_000_000,
}


class TestPortfolioIntraExchangeTransfers:
    @respx.mock
    def test_returns_page(self, portfolio: PortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/intra_exchange_instance_transfers"
        ).mock(
            return_value=httpx.Response(
                200, json={"transfers": [_TRANSFER], "cursor": "next"}
            )
        )
        page = portfolio.intra_exchange_transfers(limit=10)
        assert len(page.items) == 1
        t = page.items[0]
        assert t.transfer_id == "xfer-1"
        assert t.source == "event_contract"
        assert t.destination == "margined"
        assert t.amount == Decimal("25.5000")
        assert t.status == "complete"
        assert page.cursor == "next"

    @respx.mock
    def test_all_paginates(self, portfolio: PortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/intra_exchange_instance_transfers"
        ).mock(
            side_effect=[
                httpx.Response(
                    200, json={"transfers": [{**_TRANSFER, "transfer_id": "a"}], "cursor": "c1"}
                ),
                httpx.Response(
                    200, json={"transfers": [{**_TRANSFER, "transfer_id": "b"}], "cursor": ""}
                ),
            ]
        )
        ids = [t.transfer_id for t in portfolio.intra_exchange_transfers_all()]
        assert ids == ["a", "b"]

    @respx.mock
    def test_get_by_id(self, portfolio: PortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/"
            "intra_exchange_instance_transfers/xfer-1"
        ).mock(return_value=httpx.Response(200, json={"transfer": _TRANSFER}))
        t = portfolio.get_intra_exchange_transfer("xfer-1")
        assert t.transfer_id == "xfer-1"
        assert t.amount == Decimal("25.5000")

    def test_requires_auth(self, unauth_portfolio: PortfolioResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_portfolio.intra_exchange_transfers()
        with pytest.raises(AuthRequiredError):
            unauth_portfolio.get_intra_exchange_transfer("xfer-1")


class TestAsyncPortfolioIntraExchangeTransfers:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_page(self, async_portfolio: AsyncPortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/intra_exchange_instance_transfers"
        ).mock(
            return_value=httpx.Response(
                200, json={"transfers": [_TRANSFER], "cursor": ""}
            )
        )
        page = await async_portfolio.intra_exchange_transfers()
        assert len(page.items) == 1
        assert page.items[0].transfer_id == "xfer-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_by_id(self, async_portfolio: AsyncPortfolioResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/"
            "intra_exchange_instance_transfers/xfer-1"
        ).mock(return_value=httpx.Response(200, json={"transfer": _TRANSFER}))
        t = await async_portfolio.get_intra_exchange_transfer("xfer-1")
        assert t.status == "complete"

    @pytest.mark.asyncio
    async def test_requires_auth(
        self, unauth_async_portfolio: AsyncPortfolioResource
    ) -> None:
        with pytest.raises(AuthRequiredError):
            await unauth_async_portfolio.intra_exchange_transfers()
