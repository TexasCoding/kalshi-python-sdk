"""Tests for kalshi.resources.exchange — Exchange resource."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiServerError
from kalshi.resources.exchange import AsyncExchangeResource, ExchangeResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def exchange(test_auth: KalshiAuth, config: KalshiConfig) -> ExchangeResource:
    return ExchangeResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_exchange(
    test_auth: KalshiAuth, config: KalshiConfig
) -> AsyncExchangeResource:
    return AsyncExchangeResource(AsyncTransport(test_auth, config))


# ── Sync tests ──────────────────────────────────────────────


class TestExchangeStatus:
    @respx.mock
    def test_returns_status(self, exchange: ExchangeResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "exchange_active": True,
                    "trading_active": True,
                },
            )
        )
        status = exchange.status()
        assert status.exchange_active is True
        assert status.trading_active is True
        assert status.exchange_estimated_resume_time is None

    @respx.mock
    def test_maintenance_mode(self, exchange: ExchangeResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "exchange_active": True,
                    "trading_active": False,
                    "exchange_estimated_resume_time": "2026-04-13T06:00:00Z",
                },
            )
        )
        status = exchange.status()
        assert status.exchange_active is True
        assert status.trading_active is False
        assert status.exchange_estimated_resume_time is not None

    @respx.mock
    def test_null_resume_time(self, exchange: ExchangeResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "exchange_active": False,
                    "trading_active": False,
                    "exchange_estimated_resume_time": None,
                },
            )
        )
        status = exchange.status()
        assert status.exchange_active is False
        assert status.exchange_estimated_resume_time is None


class TestExchangeSchedule:
    @respx.mock
    def test_returns_schedule(self, exchange: ExchangeResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/schedule").mock(
            return_value=httpx.Response(
                200,
                json={
                    "schedule": {
                        "standard_hours": [
                            {
                                "start_time": "2026-01-01T00:00:00Z",
                                "end_time": "2026-12-31T23:59:59Z",
                                "monday": [{"open_time": "00:00", "close_time": "23:59"}],
                                "tuesday": [{"open_time": "00:00", "close_time": "23:59"}],
                                "wednesday": [],
                                "thursday": [],
                                "friday": [],
                                "saturday": [],
                                "sunday": [],
                            }
                        ],
                        "maintenance_windows": [
                            {
                                "start_datetime": "2026-04-15T04:00:00Z",
                                "end_datetime": "2026-04-15T06:00:00Z",
                            }
                        ],
                    }
                },
            )
        )
        schedule = exchange.schedule()
        assert len(schedule.standard_hours) == 1
        assert len(schedule.standard_hours[0].monday) == 1
        assert schedule.standard_hours[0].monday[0].open_time == "00:00"
        assert len(schedule.standard_hours[0].wednesday) == 0
        assert len(schedule.maintenance_windows) == 1

    @respx.mock
    def test_empty_schedule(self, exchange: ExchangeResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/schedule").mock(
            return_value=httpx.Response(
                200,
                json={
                    "schedule": {
                        "standard_hours": [],
                        "maintenance_windows": [],
                    }
                },
            )
        )
        schedule = exchange.schedule()
        assert schedule.standard_hours == []
        assert schedule.maintenance_windows == []


class TestExchangeAnnouncements:
    @respx.mock
    def test_returns_announcements(self, exchange: ExchangeResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/announcements").mock(
            return_value=httpx.Response(
                200,
                json={
                    "announcements": [
                        {
                            "type": "info",
                            "message": "Exchange will be down for maintenance.",
                            "delivery_time": "2026-04-13T00:00:00Z",
                            "status": "active",
                        },
                        {
                            "type": "warning",
                            "message": "High volatility expected.",
                            "delivery_time": "2026-04-12T12:00:00Z",
                            "status": "active",
                        },
                    ]
                },
            )
        )
        announcements = exchange.announcements()
        assert len(announcements) == 2
        assert announcements[0].type == "info"
        assert announcements[0].message == "Exchange will be down for maintenance."
        assert announcements[0].status == "active"
        assert announcements[1].type == "warning"

    @respx.mock
    def test_empty_announcements(self, exchange: ExchangeResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/announcements").mock(
            return_value=httpx.Response(
                200,
                json={"announcements": []},
            )
        )
        announcements = exchange.announcements()
        assert announcements == []


# ── Async tests ─────────────────────────────────────────────


class TestAsyncExchangeStatus:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_status(
        self, async_exchange: AsyncExchangeResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "exchange_active": True,
                    "trading_active": True,
                },
            )
        )
        status = await async_exchange.status()
        assert status.exchange_active is True
        assert status.trading_active is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_maintenance_mode(
        self, async_exchange: AsyncExchangeResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "exchange_active": True,
                    "trading_active": False,
                    "exchange_estimated_resume_time": "2026-04-13T06:00:00Z",
                },
            )
        )
        status = await async_exchange.status()
        assert status.trading_active is False
        assert status.exchange_estimated_resume_time is not None


class TestAsyncExchangeSchedule:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_schedule(
        self, async_exchange: AsyncExchangeResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/schedule").mock(
            return_value=httpx.Response(
                200,
                json={
                    "schedule": {
                        "standard_hours": [
                            {
                                "start_time": "2026-01-01T00:00:00Z",
                                "end_time": "2026-12-31T23:59:59Z",
                                "monday": [{"open_time": "00:00", "close_time": "23:59"}],
                                "tuesday": [],
                                "wednesday": [],
                                "thursday": [],
                                "friday": [],
                                "saturday": [],
                                "sunday": [],
                            }
                        ],
                        "maintenance_windows": [],
                    }
                },
            )
        )
        schedule = await async_exchange.schedule()
        assert len(schedule.standard_hours) == 1
        assert schedule.standard_hours[0].monday[0].open_time == "00:00"


class TestUserDataTimestamp:
    @respx.mock
    def test_returns_timestamp(self, exchange: ExchangeResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/exchange/user_data_timestamp"
        ).mock(
            return_value=httpx.Response(
                200, json={"as_of_time": "2026-04-19T12:34:56Z"},
            )
        )
        result = exchange.user_data_timestamp()
        assert result.as_of_time.year == 2026
        assert result.as_of_time.month == 4
        assert result.as_of_time.day == 19

    @respx.mock
    def test_server_error(self, exchange: ExchangeResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/exchange/user_data_timestamp"
        ).mock(return_value=httpx.Response(500, json={"error": "internal"}))
        with pytest.raises(KalshiServerError):
            exchange.user_data_timestamp()


class TestAsyncUserDataTimestamp:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_timestamp(
        self, async_exchange: AsyncExchangeResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/exchange/user_data_timestamp"
        ).mock(
            return_value=httpx.Response(
                200, json={"as_of_time": "2026-04-19T12:34:56Z"},
            )
        )
        result = await async_exchange.user_data_timestamp()
        assert result.as_of_time.year == 2026

    @respx.mock
    @pytest.mark.asyncio
    async def test_server_error(
        self, async_exchange: AsyncExchangeResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/exchange/user_data_timestamp"
        ).mock(return_value=httpx.Response(500, json={"error": "internal"}))
        with pytest.raises(KalshiServerError):
            await async_exchange.user_data_timestamp()


class TestAsyncExchangeAnnouncements:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_announcements(
        self, async_exchange: AsyncExchangeResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/announcements").mock(
            return_value=httpx.Response(
                200,
                json={
                    "announcements": [
                        {
                            "type": "error",
                            "message": "System issue detected.",
                            "delivery_time": "2026-04-13T00:00:00Z",
                            "status": "inactive",
                        }
                    ]
                },
            )
        )
        announcements = await async_exchange.announcements()
        assert len(announcements) == 1
        assert announcements[0].type == "error"
        assert announcements[0].status == "inactive"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_announcements(
        self, async_exchange: AsyncExchangeResource
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/exchange/announcements").mock(
            return_value=httpx.Response(200, json={"announcements": []})
        )
        announcements = await async_exchange.announcements()
        assert announcements == []
