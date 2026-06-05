"""Integration tests for perps balance / risk / exchange access — live demo.

Covers the ``MarginAccountResource`` (``balance`` / ``risk`` /
``notional_risk_limit`` / ``fee_tiers``) and the ``PerpsExchangeResource``
(``status`` / ``enabled`` / ``risk_parameters``).

``status`` and ``risk_parameters`` are public; ``enabled`` and the whole
margin-account surface are auth-gated and require a margin-enabled demo account
(guarded with ``skip_if_not_margin_enabled``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from kalshi.models.common import Page
from kalshi.perps.async_client import AsyncPerpsClient
from kalshi.perps.client import PerpsClient
from kalshi.perps.models.exchange import (
    ExchangeStatus,
    GetMarginRiskParametersResponse,
    MarginEnabledResponse,
)
from kalshi.perps.models.margin_account import (
    GetMarginBalanceResponse,
    GetMarginFeeTiersResponse,
    GetMarginRiskResponse,
    NotionalRiskLimitResponse,
)
from kalshi.perps.models.portfolio import (
    GetMarginPositionsResponse,
    MarginFill,
    MarginTrade,
)
from tests.integration.conftest import skip_if_not_margin_enabled
from tests.integration.coverage_harness import register_perps

register_perps(
    "PerpsExchangeResource",
    ["enabled", "risk_parameters", "status"],
)
register_perps(
    "MarginAccountResource",
    ["balance", "fee_tiers", "notional_risk_limit", "risk"],
)
register_perps(
    "PerpsPortfolioResource",
    ["fills", "fills_all", "positions", "trades", "trades_all"],
)


@pytest.mark.integration
class TestPerpsExchangeSync:
    def test_status(self, perps_sync_client: PerpsClient) -> None:
        """Public — no auth required."""
        status = perps_sync_client.exchange.status()
        assert isinstance(status, ExchangeStatus)
        assert isinstance(status.exchange_active, bool)
        assert isinstance(status.trading_active, bool)

    def test_risk_parameters(self, perps_sync_client: PerpsClient) -> None:
        """Public — no auth required."""
        params = perps_sync_client.exchange.risk_parameters()
        assert isinstance(params, GetMarginRiskParametersResponse)
        assert isinstance(params.liquidation_margin_ratio_threshold, Decimal)
        assert isinstance(params.initial_margin_multiplier, dict)

    def test_enabled(self, perps_sync_client: PerpsClient) -> None:
        if not perps_sync_client.is_authenticated:
            pytest.skip("Perps client unauthenticated — enabled() requires auth")
        resp = perps_sync_client.exchange.enabled()
        assert isinstance(resp, MarginEnabledResponse)
        assert isinstance(resp.enabled, bool)


@pytest.mark.integration
class TestPerpsBalanceRiskSync:
    def test_balance(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        balance = perps_sync_client.margin.balance()
        assert isinstance(balance, GetMarginBalanceResponse)
        assert isinstance(balance.settled_funds, Decimal)
        assert isinstance(balance.subaccount_balances, list)
        for sub in balance.subaccount_balances:
            assert isinstance(sub.account_equity, Decimal)
            assert isinstance(sub.maintenance_margin, Decimal)
            assert isinstance(sub.position_value, Decimal)
            assert isinstance(sub.available_balance, Decimal)

    def test_risk(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        risk = perps_sync_client.margin.risk()
        assert isinstance(risk, GetMarginRiskResponse)
        assert isinstance(risk.total_maintenance_margin, Decimal)
        assert isinstance(risk.total_position_notional, Decimal)
        assert isinstance(risk.positions, list)
        for pos in risk.positions:
            assert pos.market_ticker
            assert isinstance(pos.mark_price, Decimal)
            # liquidation price + leverage are optional (only set on open positions)
            if pos.estimated_liquidation_price is not None:
                assert isinstance(pos.estimated_liquidation_price, Decimal)
            if pos.position_leverage is not None:
                assert isinstance(pos.position_leverage, float)

    def test_notional_risk_limit(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        resp = perps_sync_client.margin.notional_risk_limit()
        assert isinstance(resp, NotionalRiskLimitResponse)
        assert isinstance(resp.default_notional_value_risk_limit, Decimal)

    def test_fee_tiers(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        resp = perps_sync_client.margin.fee_tiers()
        assert isinstance(resp, GetMarginFeeTiersResponse)
        assert isinstance(resp.maker_fee_rates, dict)
        assert isinstance(resp.taker_fee_rates, dict)


@pytest.mark.integration
class TestPerpsPortfolioSync:
    def test_positions(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        resp = perps_sync_client.portfolio.positions()
        assert isinstance(resp, GetMarginPositionsResponse)
        assert isinstance(resp.positions, list)
        for pos in resp.positions:
            assert pos.market_ticker
            assert isinstance(pos.entry_price, Decimal)

    def test_fills(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        page = perps_sync_client.portfolio.fills(limit=5)
        assert isinstance(page, Page)
        for fill in page.items:
            assert isinstance(fill, MarginFill)
            assert fill.fill_id

    def test_fills_all(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        for count, fill in enumerate(perps_sync_client.portfolio.fills_all(limit=5)):
            assert isinstance(fill, MarginFill)
            if count >= 2:
                break

    def test_trades(
        self, perps_sync_client: PerpsClient, perps_market_ticker: str
    ) -> None:
        """Public — no auth required; ``ticker`` is mandatory."""
        page = perps_sync_client.portfolio.trades(ticker=perps_market_ticker, limit=5)
        assert isinstance(page, Page)
        for trade in page.items:
            assert isinstance(trade, MarginTrade)
            assert trade.ticker == perps_market_ticker
            assert isinstance(trade.price, Decimal)

    def test_trades_all(
        self, perps_sync_client: PerpsClient, perps_market_ticker: str
    ) -> None:
        for count, trade in enumerate(
            perps_sync_client.portfolio.trades_all(ticker=perps_market_ticker, limit=5)
        ):
            assert isinstance(trade, MarginTrade)
            if count >= 2:
                break


@pytest.mark.integration
class TestPerpsBalanceRiskAsync:
    async def test_status(self, perps_async_client: AsyncPerpsClient) -> None:
        status = await perps_async_client.exchange.status()
        assert isinstance(status, ExchangeStatus)

    async def test_balance(self, perps_async_client: AsyncPerpsClient) -> None:
        if not perps_async_client.is_authenticated:
            pytest.skip("Perps client unauthenticated")
        if not (await perps_async_client.exchange.enabled()).enabled:
            pytest.skip("Demo account is not margin-enabled")
        balance = await perps_async_client.margin.balance()
        assert isinstance(balance, GetMarginBalanceResponse)
        assert isinstance(balance.settled_funds, Decimal)

    async def test_risk(self, perps_async_client: AsyncPerpsClient) -> None:
        if not perps_async_client.is_authenticated:
            pytest.skip("Perps client unauthenticated")
        if not (await perps_async_client.exchange.enabled()).enabled:
            pytest.skip("Demo account is not margin-enabled")
        risk = await perps_async_client.margin.risk()
        assert isinstance(risk, GetMarginRiskResponse)
        assert isinstance(risk.total_maintenance_margin, Decimal)
