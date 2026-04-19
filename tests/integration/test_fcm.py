"""Integration tests for FcmResource.

Demo-supported per Path B audit (2026-04-18). Demo services these
endpoints but non-FCM accounts typically see empty results or 4xx.
Tests tolerate both — they assert shape, not content.
"""

from __future__ import annotations

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiAuthError, KalshiError, KalshiNotFoundError
from kalshi.models.orders import Order
from kalshi.models.portfolio import PositionsResponse
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

register("FcmResource", ["orders", "orders_all", "positions"])

_TOLERATED_FCM_ERRORS: tuple[type[Exception], ...] = (
    KalshiAuthError,
    KalshiNotFoundError,
    KalshiError,
)


@pytest.mark.integration
class TestFcmSync:
    def test_orders(self, sync_client: KalshiClient) -> None:
        try:
            page = sync_client.fcm.orders(subtrader_id="sdk-test-subtrader")
        except _TOLERATED_FCM_ERRORS:
            pytest.skip("Demo account is not FCM-enabled (expected)")
        assert isinstance(page.items, list)
        for item in page.items:
            assert isinstance(item, Order)
            assert_model_fields(item)

    def test_orders_all(self, sync_client: KalshiClient) -> None:
        try:
            gen = sync_client.fcm.orders_all(subtrader_id="sdk-test-subtrader")
            for count, item in enumerate(gen):
                assert isinstance(item, Order)
                if count >= 9:
                    break
        except _TOLERATED_FCM_ERRORS:
            pytest.skip("Demo account is not FCM-enabled (expected)")

    def test_positions(self, sync_client: KalshiClient) -> None:
        try:
            result = sync_client.fcm.positions(
                subtrader_id="sdk-test-subtrader",
            )
        except _TOLERATED_FCM_ERRORS:
            pytest.skip("Demo account is not FCM-enabled (expected)")
        assert isinstance(result, PositionsResponse)
        assert_model_fields(result)


@pytest.mark.integration
class TestFcmAsync:
    async def test_orders(self, async_client: AsyncKalshiClient) -> None:
        try:
            page = await async_client.fcm.orders(
                subtrader_id="sdk-test-subtrader",
            )
        except _TOLERATED_FCM_ERRORS:
            pytest.skip("Demo account is not FCM-enabled (expected)")
        assert isinstance(page.items, list)

    async def test_positions(self, async_client: AsyncKalshiClient) -> None:
        try:
            result = await async_client.fcm.positions(
                subtrader_id="sdk-test-subtrader",
            )
        except _TOLERATED_FCM_ERRORS:
            pytest.skip("Demo account is not FCM-enabled (expected)")
        assert isinstance(result, PositionsResponse)
