"""Integration tests for the perps (margin) funding resource — live demo.

Covers ``rate_estimate`` / ``historical_rates`` / ``history``. ``rate_estimate``
and ``historical_rates`` are public; ``history`` is auth-gated (per-user payment
history) and requires a margin-enabled demo account.

Field-type note: ``funding_rate`` is a spec ``number/format: double`` and is a
plain ``float`` (NOT a price ``DollarDecimal``) on every funding model.
"""

from __future__ import annotations

import time
from datetime import datetime

import pytest

from kalshi.perps.async_client import AsyncPerpsClient
from kalshi.perps.client import PerpsClient
from kalshi.perps.models.funding import (
    MarginFundingHistoryEntry,
    MarginFundingRate,
    MarginFundingRateEstimate,
)
from tests.integration.conftest import skip_if_not_margin_enabled
from tests.integration.coverage_harness import register_perps

register_perps(
    "FundingResource",
    ["history", "historical_rates", "rate_estimate"],
)


@pytest.mark.integration
class TestPerpsFundingSync:
    def test_rate_estimate(
        self, perps_sync_client: PerpsClient, perps_market_ticker: str
    ) -> None:
        est = perps_sync_client.funding.rate_estimate(perps_market_ticker)
        assert isinstance(est, MarginFundingRateEstimate)
        # funding_rate is a plain float when present (optional on the estimate).
        if est.funding_rate is not None:
            assert isinstance(est.funding_rate, float)
        assert isinstance(est.next_funding_time, datetime)

    def test_historical_rates(self, perps_sync_client: PerpsClient) -> None:
        rates = perps_sync_client.funding.historical_rates()
        assert isinstance(rates, list)
        for rate in rates:
            assert isinstance(rate, MarginFundingRate)
            assert isinstance(rate.funding_rate, float)
            assert rate.market_ticker
            assert isinstance(rate.funding_time, datetime)

    def test_history(self, perps_sync_client: PerpsClient) -> None:
        skip_if_not_margin_enabled(perps_sync_client)
        now = time.gmtime()
        end_date = time.strftime("%Y-%m-%d", now)
        start_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400 * 7))
        history = perps_sync_client.funding.history(
            start_date=start_date, end_date=end_date
        )
        assert isinstance(history, list)
        for entry in history:
            assert isinstance(entry, MarginFundingHistoryEntry)
            assert isinstance(entry.funding_rate, float)
            assert entry.market_ticker


@pytest.mark.integration
class TestPerpsFundingAsync:
    async def test_rate_estimate(self, perps_async_client: AsyncPerpsClient) -> None:
        markets = await perps_async_client.markets.list()
        if not markets:
            pytest.skip("No margin markets on demo server")
        est = await perps_async_client.funding.rate_estimate(markets[0].ticker)
        assert isinstance(est, MarginFundingRateEstimate)
        if est.funding_rate is not None:
            assert isinstance(est.funding_rate, float)
        assert isinstance(est.next_funding_time, datetime)

    async def test_historical_rates(
        self, perps_async_client: AsyncPerpsClient
    ) -> None:
        rates = await perps_async_client.funding.historical_rates()
        assert isinstance(rates, list)
        for rate in rates:
            assert isinstance(rate, MarginFundingRate)
            assert isinstance(rate.funding_rate, float)
