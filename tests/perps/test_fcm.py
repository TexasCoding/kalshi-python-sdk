"""Tests for perps FCM create_subtrader (POST /margin/fcm/subtraders)."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import AuthRequiredError
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.fcm import (
    CreateMarginFCMSubtraderRequest,
    CreateMarginFCMSubtraderResponse,
    UpdateFCMSubtraderRiskControlsRequest,
)

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


class TestCreateMarginFCMSubtraderRequest:
    def test_serializes(self) -> None:
        req = CreateMarginFCMSubtraderRequest(subtrader_suffix="desk1")
        assert req.model_dump(exclude_none=True, by_alias=True, mode="json") == {
            "subtrader_suffix": "desk1"
        }

    def test_rejects_bad_suffix(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMSubtraderRequest(subtrader_suffix="BAD_SUFFIX")

    def test_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMSubtraderRequest(  # type: ignore[call-arg]
                subtrader_suffix="desk1", phantom=1
            )


class TestFcmCreateSubtrader:
    @respx.mock
    def test_create_subtrader_sends_body(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "user_desk1"})
        )
        resp = perps_client.fcm.create_subtrader(subtrader_suffix="desk1")
        assert isinstance(resp, CreateMarginFCMSubtraderResponse)
        assert resp.subtrader_id == "user_desk1"
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_suffix": "desk1"
        }

    @respx.mock
    def test_create_subtrader_with_request_model(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "user_a"})
        )
        req = CreateMarginFCMSubtraderRequest(subtrader_suffix="a")
        resp = perps_client.fcm.create_subtrader(request=req)
        assert resp.subtrader_id == "user_a"
        assert route.called

    def test_requires_args(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError, match="create_subtrader"):
            perps_client.fcm.create_subtrader()  # type: ignore[call-overload]

    def test_unauthenticated_raises(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo(max_retries=0))
        with pytest.raises(AuthRequiredError):
            client.fcm.create_subtrader(subtrader_suffix="desk1")


class TestUpdateFCMSubtraderRiskControlsRequest:
    def test_serializes(self) -> None:
        req = UpdateFCMSubtraderRiskControlsRequest(
            subtrader_id="user_desk1",
            im_cap=Decimal("100.0000"),
            market_ticker="BTC-PERP",
        )
        assert req.model_dump(exclude_none=True, by_alias=True, mode="json") == {
            "subtrader_id": "user_desk1",
            "im_cap": "100.0000",
            "market_ticker": "BTC-PERP",
        }

    def test_rejects_negative_im_cap(self) -> None:
        with pytest.raises(ValidationError):
            UpdateFCMSubtraderRiskControlsRequest(
                subtrader_id="user_desk1",
                im_cap=Decimal("-1.00"),
            )

    def test_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            UpdateFCMSubtraderRiskControlsRequest(  # type: ignore[call-arg]
                subtrader_id="user_desk1",
                im_cap=Decimal("1.00"),
                phantom=1,
            )


class TestFcmRiskControls:
    @respx.mock
    def test_get_risk_controls(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(
                200,
                json={
                    "risk_controls": [
                        {
                            "subtrader_id": "user_desk1",
                            "im_cap": "100.0000",
                        },
                        {
                            "subtrader_id": "user_desk1",
                            "market_ticker": "BTC-PERP",
                            "im_cap": "25.5000",
                        },
                    ]
                },
            )
        )
        resp = perps_client.fcm.risk_controls(subtrader_id="user_desk1")
        assert len(resp.risk_controls) == 2
        assert resp.risk_controls[0].market_ticker is None
        assert resp.risk_controls[0].im_cap == Decimal("100.0000")
        assert resp.risk_controls[1].market_ticker == "BTC-PERP"
        assert dict(route.calls[0].request.url.params) == {"subtrader_id": "user_desk1"}

    @respx.mock
    def test_get_risk_controls_filters_market(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={"risk_controls": []})
        )
        perps_client.fcm.risk_controls(subtrader_id="user_desk1", market_ticker="ETH-PERP")
        assert dict(route.calls[0].request.url.params) == {
            "subtrader_id": "user_desk1",
            "market_ticker": "ETH-PERP",
        }

    @respx.mock
    def test_get_risk_controls_filters_asset_class(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={"risk_controls": []})
        )
        perps_client.fcm.risk_controls(subtrader_id="user_desk1", asset_class="Crypto")
        assert dict(route.calls[0].request.url.params) == {
            "subtrader_id": "user_desk1",
            "asset_class": "Crypto",
        }

    @respx.mock
    def test_update_risk_controls_kwargs(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.fcm.update_risk_controls(
            subtrader_id="user_desk1",
            im_cap=Decimal("50.0000"),
            market_ticker="BTC-PERP",
        )
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_id": "user_desk1",
            "im_cap": "50.0000",
            "market_ticker": "BTC-PERP",
        }

    @respx.mock
    def test_update_risk_controls_asset_class(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.fcm.update_risk_controls(
            subtrader_id="user_desk1",
            im_cap=Decimal("50.0000"),
            asset_class="Equities",
        )
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_id": "user_desk1",
            "im_cap": "50.0000",
            "asset_class": "Equities",
        }

    @respx.mock
    def test_update_risk_controls_request_model(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={})
        )
        req = UpdateFCMSubtraderRiskControlsRequest(
            subtrader_id="user_a",
            im_cap=Decimal("10.00"),
        )
        perps_client.fcm.update_risk_controls(request=req)
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_id": "user_a",
            "im_cap": "10.00",
        }
        assert route.called

    def test_update_requires_args(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError, match="update_risk_controls"):
            perps_client.fcm.update_risk_controls()  # type: ignore[call-overload]

    @respx.mock
    def test_delete_risk_controls(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.fcm.delete_risk_controls(
            subtrader_id="user_desk1",
            market_ticker="BTC-PERP",
        )
        assert dict(route.calls[0].request.url.params) == {
            "subtrader_id": "user_desk1",
            "market_ticker": "BTC-PERP",
        }

    @respx.mock
    def test_delete_risk_controls_asset_class(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.fcm.delete_risk_controls(
            subtrader_id="user_desk1",
            asset_class="Crypto",
        )
        assert dict(route.calls[0].request.url.params) == {
            "subtrader_id": "user_desk1",
            "asset_class": "Crypto",
        }

    def test_unauthenticated_raises(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo(max_retries=0))
        with pytest.raises(AuthRequiredError):
            client.fcm.risk_controls(subtrader_id="user_desk1")
        with pytest.raises(AuthRequiredError):
            client.fcm.update_risk_controls(subtrader_id="user_desk1", im_cap=Decimal("1"))
        with pytest.raises(AuthRequiredError):
            client.fcm.delete_risk_controls(subtrader_id="user_desk1")


class TestAsyncFcmRiskControls:
    @respx.mock
    @pytest.mark.asyncio
    async def test_async_roundtrip(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.get(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(
                200,
                json={
                    "risk_controls": [
                        {"subtrader_id": "user_desk1", "im_cap": "1.0000"},
                    ]
                },
            )
        )
        respx.put(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.delete(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={})
        )
        resp = await async_perps_client.fcm.risk_controls(subtrader_id="user_desk1")
        assert resp.risk_controls[0].im_cap == Decimal("1.0000")
        await async_perps_client.fcm.update_risk_controls(
            subtrader_id="user_desk1",
            im_cap=Decimal("2.00"),
        )
        await async_perps_client.fcm.delete_risk_controls(subtrader_id="user_desk1")
