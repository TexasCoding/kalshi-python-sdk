"""Tests for the perps funding resource (#395).

Covers ``rate_estimate``, ``historical_rates``, and ``history`` (sync + async):
happy path, edge cases, error mapping, and the auth gate on ``history``.
"""

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
from kalshi.perps.models.funding import (
    MarginFundingHistoryEntry,
    MarginFundingRate,
)

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


# ── rate_estimate ─────────────────────────────────────────────────────────────


class TestRateEstimate:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/funding_rates/estimate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "market_ticker": "BTC-PERP",
                    "computed_time": "2026-06-04T12:00:00Z",
                    "funding_rate": 0.000125,
                    "mark_price_dollars": "65000.50",
                    "next_funding_time": "2026-06-04T16:00:00Z",
                },
            )
        )
        est = perps_client.funding.rate_estimate("BTC-PERP")
        # mark_price -> Decimal, funding_rate -> float, next_funding_time aware.
        assert isinstance(est.mark_price, Decimal)
        assert est.mark_price == Decimal("65000.50")
        assert isinstance(est.funding_rate, float)
        assert est.funding_rate == 0.000125
        assert isinstance(est.next_funding_time, datetime)
        assert est.next_funding_time.tzinfo is not None
        assert est.market_ticker == "BTC-PERP"
        # ticker propagated to the query string.
        assert route.calls.last.request.url.params["ticker"] == "BTC-PERP"

    @respx.mock
    def test_edge_only_required_field(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/estimate").mock(
            return_value=httpx.Response(
                200, json={"next_funding_time": "2026-06-04T16:00:00Z"}
            )
        )
        est = perps_client.funding.rate_estimate("BTC-PERP")
        assert est.market_ticker is None
        assert est.computed_time is None
        assert est.funding_rate is None
        assert est.mark_price is None
        assert isinstance(est.next_funding_time, datetime)

    @respx.mock
    def test_error_400_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/estimate").mock(
            return_value=httpx.Response(400, json={"error": {"code": "bad_request"}})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.funding.rate_estimate("BTC-PERP")

    @respx.mock
    def test_missing_required_field_raises(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/estimate").mock(
            return_value=httpx.Response(200, json={"market_ticker": "BTC-PERP"})
        )
        with pytest.raises(ValidationError):
            perps_client.funding.rate_estimate("BTC-PERP")

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/estimate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "funding_rate": 0.0002,
                    "mark_price_dollars": "100.0000",
                    "next_funding_time": "2026-06-04T16:00:00Z",
                },
            )
        )
        est = await async_perps_client.funding.rate_estimate("ETH-PERP")
        assert est.mark_price == Decimal("100.0000")
        assert isinstance(est.next_funding_time, datetime)
        await async_perps_client.close()


# ── historical_rates ──────────────────────────────────────────────────────────


class TestHistoricalRates:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/funding_rates/historical").mock(
            return_value=httpx.Response(
                200,
                json={
                    "funding_rates": [
                        {
                            "market_ticker": "BTC-PERP",
                            "funding_time": "2026-06-04T08:00:00Z",
                            "funding_rate": 0.0001,
                            "mark_price_dollars": "64000.00",
                        },
                        {
                            "market_ticker": "BTC-PERP",
                            "funding_time": "2026-06-04T12:00:00Z",
                            "funding_rate": -0.0002,
                            "mark_price_dollars": "65000.00",
                        },
                    ]
                },
            )
        )
        rates = perps_client.funding.historical_rates(
            ticker="BTC-PERP", start_ts=1000, end_ts=2000
        )
        assert len(rates) == 2
        assert all(isinstance(r, MarginFundingRate) for r in rates)
        assert isinstance(rates[0].mark_price, Decimal)
        assert rates[0].mark_price == Decimal("64000.00")
        assert isinstance(rates[1].funding_rate, float)
        assert rates[1].funding_rate == -0.0002
        params = route.calls.last.request.url.params
        assert params["ticker"] == "BTC-PERP"
        assert params["start_ts"] == "1000"
        assert params["end_ts"] == "2000"

    @respx.mock
    def test_optional_params_omitted_when_none(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/funding_rates/historical").mock(
            return_value=httpx.Response(200, json={"funding_rates": []})
        )
        perps_client.funding.historical_rates()
        params = route.calls.last.request.url.params
        assert "ticker" not in params
        assert "start_ts" not in params
        assert "end_ts" not in params

    @respx.mock
    def test_edge_empty_array(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/historical").mock(
            return_value=httpx.Response(200, json={"funding_rates": []})
        )
        assert perps_client.funding.historical_rates() == []

    @respx.mock
    def test_edge_missing_key(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/historical").mock(
            return_value=httpx.Response(200, json={})
        )
        assert perps_client.funding.historical_rates() == []

    @respx.mock
    def test_error_500_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/historical").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(KalshiServerError):
            perps_client.funding.historical_rates()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_rates/historical").mock(
            return_value=httpx.Response(
                200,
                json={
                    "funding_rates": [
                        {
                            "market_ticker": "ETH-PERP",
                            "funding_time": "2026-06-04T08:00:00Z",
                            "funding_rate": 0.0003,
                            "mark_price_dollars": "3000.00",
                        }
                    ]
                },
            )
        )
        rates = await async_perps_client.funding.historical_rates(ticker="ETH-PERP")
        assert len(rates) == 1
        assert rates[0].mark_price == Decimal("3000.00")
        await async_perps_client.close()


# ── history ───────────────────────────────────────────────────────────────────


def _entry(*, funding_amount: str, subaccount_number: int | None) -> dict[str, object]:
    return {
        "market_ticker": "BTC-PERP",
        "funding_time": "2026-06-04T08:00:00Z",
        "funding_rate": 0.0001,
        "mark_price_dollars": "64000.00",
        "funding_amount_dollars": funding_amount,
        "quantity_fp": "10.00",
        "subaccount_number": subaccount_number,
    }


class TestHistory:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(
                200,
                json={
                    "funding_history": [
                        _entry(funding_amount="12.50", subaccount_number=0),
                        _entry(funding_amount="-7.25", subaccount_number=None),
                    ]
                },
            )
        )
        entries = perps_client.funding.history(
            start_date="2026-06-01",
            end_date="2026-06-04",
            ticker="BTC-PERP",
            subaccount=0,
        )
        assert len(entries) == 2
        assert all(isinstance(e, MarginFundingHistoryEntry) for e in entries)
        # Decimal typing on dollar/count fields; positive & negative amounts.
        assert isinstance(entries[0].funding_amount, Decimal)
        assert entries[0].funding_amount == Decimal("12.50")
        assert entries[1].funding_amount == Decimal("-7.25")
        assert isinstance(entries[0].mark_price, Decimal)
        assert isinstance(entries[0].quantity, Decimal)
        assert entries[0].quantity == Decimal("10.00")
        # subaccount_number: 0 and explicit null both parse.
        assert entries[0].subaccount_number == 0
        assert entries[1].subaccount_number is None
        # Query string carries all four params.
        params = route.calls.last.request.url.params
        assert params["start_date"] == "2026-06-01"
        assert params["end_date"] == "2026-06-04"
        assert params["ticker"] == "BTC-PERP"
        assert params["subaccount"] == "0"

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(200, json={"funding_history": []})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.funding.history(start_date="2026-06-01", end_date="2026-06-04")
        assert not route.called  # no HTTP issued
        client.close()

    @respx.mock
    def test_edge_empty_array(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(200, json={"funding_history": []})
        )
        out = perps_client.funding.history(start_date="2026-06-01", end_date="2026-06-04")
        assert out == []

    @respx.mock
    def test_edge_missing_subaccount_key_raises(self, perps_client: PerpsClient) -> None:
        bad = _entry(funding_amount="1.00", subaccount_number=0)
        del bad["subaccount_number"]
        respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(200, json={"funding_history": [bad]})
        )
        with pytest.raises(ValidationError):
            perps_client.funding.history(start_date="2026-06-01", end_date="2026-06-04")

    @respx.mock
    def test_optional_params_omitted(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(200, json={"funding_history": []})
        )
        perps_client.funding.history(start_date="2026-06-01", end_date="2026-06-04")
        params = route.calls.last.request.url.params
        assert "ticker" not in params
        assert "subaccount" not in params
        assert params["start_date"] == "2026-06-01"

    @respx.mock
    def test_error_401_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(KalshiAuthError):
            perps_client.funding.history(start_date="2026-06-01", end_date="2026-06-04")

    @respx.mock
    def test_error_403_maps(self, perps_client: PerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(403, json={"error": {"code": "forbidden"}})
        )
        with pytest.raises(KalshiAuthError):
            perps_client.funding.history(start_date="2026-06-01", end_date="2026-06-04")

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(
                200,
                json={
                    "funding_history": [_entry(funding_amount="5.00", subaccount_number=3)]
                },
            )
        )
        entries = await async_perps_client.funding.history(
            start_date="2026-06-01", end_date="2026-06-04"
        )
        assert len(entries) == 1
        assert entries[0].funding_amount == Decimal("5.00")
        assert entries[0].subaccount_number == 3
        await async_perps_client.close()

    @respx.mock
    async def test_async_unauth_raises_before_http(self) -> None:
        route = respx.get(f"{BASE}/margin/funding_history").mock(
            return_value=httpx.Response(200, json={"funding_history": []})
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            await client.funding.history(start_date="2026-06-01", end_date="2026-06-04")
        assert not route.called
        await client.close()
