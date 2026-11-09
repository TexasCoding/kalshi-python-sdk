"""Tests for perps FCM create_subtrader (POST /margin/fcm/subtraders)."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import (
    AuthRequiredError,
    KalshiConflictError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.fcm import (
    CreateMarginFCMPositionTransferRequest,
    CreateMarginFCMPositionTransferResponse,
    CreateMarginFCMSubtraderRequest,
    CreateMarginFCMSubtraderResponse,
    UpdateFCMNotionalRiskLimitRequest,
    UpdateFCMSubtraderRiskControlsRequest,
)

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


class TestCreateMarginFCMSubtraderRequest:
    def test_serializes(self) -> None:
        req = CreateMarginFCMSubtraderRequest(
            subtrader_suffix="desk1", require_category_cap=True
        )
        assert req.model_dump(exclude_none=True, by_alias=True, mode="json") == {
            "subtrader_suffix": "desk1",
            "require_category_cap": True,
        }

    def test_serializes_false(self) -> None:
        req = CreateMarginFCMSubtraderRequest(
            subtrader_suffix="desk1", require_category_cap=False
        )
        dumped = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert dumped["require_category_cap"] is False

    def test_omitted_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMSubtraderRequest(subtrader_suffix="desk1")  # type: ignore[call-arg]

    def test_rejects_wrong_type(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMSubtraderRequest(
                subtrader_suffix="desk1",
                require_category_cap=["nope"],  # type: ignore[arg-type]
            )

    def test_rejects_bad_suffix(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMSubtraderRequest(
                subtrader_suffix="BAD_SUFFIX", require_category_cap=False
            )

    def test_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMSubtraderRequest(  # type: ignore[call-arg]
                subtrader_suffix="desk1", require_category_cap=False, phantom=1
            )


class TestFcmCreateSubtrader:
    @respx.mock
    def test_create_subtrader_sends_body(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "user_desk1"})
        )
        resp = perps_client.fcm.create_subtrader(
            subtrader_suffix="desk1", require_category_cap=True
        )
        assert isinstance(resp, CreateMarginFCMSubtraderResponse)
        assert resp.subtrader_id == "user_desk1"
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_suffix": "desk1",
            "require_category_cap": True,
        }

    @respx.mock
    def test_create_subtrader_sends_false(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "user_desk1"})
        )
        perps_client.fcm.create_subtrader(
            subtrader_suffix="desk1", require_category_cap=False
        )
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_suffix": "desk1",
            "require_category_cap": False,
        }

    def test_create_subtrader_omitted_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError, match="require_category_cap"):
            perps_client.fcm.create_subtrader(  # type: ignore[call-overload]
                subtrader_suffix="desk1"
            )

    @respx.mock
    def test_create_subtrader_with_request_model(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/margin/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "user_a"})
        )
        req = CreateMarginFCMSubtraderRequest(
            subtrader_suffix="a", require_category_cap=False
        )
        resp = perps_client.fcm.create_subtrader(request=req)
        assert resp.subtrader_id == "user_a"
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_suffix": "a",
            "require_category_cap": False,
        }
        assert route.called

    def test_requires_args(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError, match="create_subtrader"):
            perps_client.fcm.create_subtrader()  # type: ignore[call-overload]

    def test_unauthenticated_raises(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo(max_retries=0))
        with pytest.raises(AuthRequiredError):
            client.fcm.create_subtrader(
                subtrader_suffix="desk1", require_category_cap=False
            )


class TestAsyncFcmCreateSubtrader:
    @respx.mock
    @pytest.mark.asyncio
    async def test_create_subtrader_sends_true(
        self, async_perps_client: AsyncPerpsClient
    ) -> None:
        route = respx.post(f"{BASE}/margin/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "user_desk1"})
        )
        resp = await async_perps_client.fcm.create_subtrader(
            subtrader_suffix="desk1", require_category_cap=True
        )
        assert resp.subtrader_id == "user_desk1"
        assert json.loads(route.calls[0].request.content) == {
            "subtrader_suffix": "desk1",
            "require_category_cap": True,
        }

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_subtrader_sends_false(
        self, async_perps_client: AsyncPerpsClient
    ) -> None:
        route = respx.post(f"{BASE}/margin/fcm/subtraders").mock(
            return_value=httpx.Response(200, json={"subtrader_id": "user_desk1"})
        )
        await async_perps_client.fcm.create_subtrader(
            subtrader_suffix="desk1", require_category_cap=False
        )
        assert json.loads(route.calls[0].request.content)["require_category_cap"] is False

    @pytest.mark.asyncio
    async def test_create_subtrader_omitted_raises(
        self, async_perps_client: AsyncPerpsClient
    ) -> None:
        with pytest.raises(TypeError, match="require_category_cap"):
            await async_perps_client.fcm.create_subtrader(  # type: ignore[call-overload]
                subtrader_suffix="desk1"
            )


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
                            "current_im": "40.0000",
                        },
                        {
                            "subtrader_id": "user_desk1",
                            "market_ticker": "BTC-PERP",
                            "im_cap": "25.5000",
                            "current_im": "10.0000",
                        },
                    ],
                    "notional_limits": [
                        {
                            "subtrader_id": "user_desk1",
                            "notional_value_risk_limit": "5000.0000",
                            "current_notional": "1250.0000",
                        }
                    ],
                },
            )
        )
        resp = perps_client.fcm.risk_controls(subtrader_id="user_desk1")
        assert len(resp.risk_controls) == 2
        assert resp.risk_controls[0].market_ticker is None
        assert resp.risk_controls[0].im_cap == Decimal("100.0000")
        assert resp.risk_controls[0].current_im == Decimal("40.0000")
        assert resp.risk_controls[1].market_ticker == "BTC-PERP"
        assert len(resp.notional_limits) == 1
        assert resp.notional_limits[0].market_ticker is None
        assert resp.notional_limits[0].current_notional == Decimal("1250.0000")
        assert dict(route.calls[0].request.url.params) == {"subtrader_id": "user_desk1"}

    @respx.mock
    def test_get_risk_controls_filters_market(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={"risk_controls": [], "notional_limits": []})
        )
        perps_client.fcm.risk_controls(subtrader_id="user_desk1", market_ticker="ETH-PERP")
        assert dict(route.calls[0].request.url.params) == {
            "subtrader_id": "user_desk1",
            "market_ticker": "ETH-PERP",
        }

    @respx.mock
    def test_get_risk_controls_filters_asset_class(self, perps_client: PerpsClient) -> None:
        route = respx.get(f"{BASE}/margin/fcm/subtraders/risk_controls").mock(
            return_value=httpx.Response(200, json={"risk_controls": [], "notional_limits": []})
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
                        {
                            "subtrader_id": "user_desk1",
                            "im_cap": "1.0000",
                            "current_im": "0.2500",
                        },
                    ],
                    "notional_limits": [],
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


class TestUpdateFCMNotionalRiskLimitRequest:
    def test_serializes(self) -> None:
        req = UpdateFCMNotionalRiskLimitRequest(notional_value_risk_limit=Decimal("5000.0000"))
        assert req.model_dump(exclude_none=True, by_alias=True, mode="json") == {
            "notional_value_risk_limit": "5000.0000",
        }

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            UpdateFCMNotionalRiskLimitRequest(notional_value_risk_limit=Decimal("-1.00"))

    def test_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            UpdateFCMNotionalRiskLimitRequest(  # type: ignore[call-arg]
                notional_value_risk_limit=Decimal("1.00"),
                phantom=1,
            )


class TestFcmNotionalRiskLimit:
    @respx.mock
    def test_update_kwargs(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/fcm/notional_risk_limit").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.fcm.update_notional_risk_limit(
            notional_value_risk_limit=Decimal("5000.0000")
        )
        assert json.loads(route.calls[0].request.content) == {
            "notional_value_risk_limit": "5000.0000",
        }

    @respx.mock
    def test_update_request_model(self, perps_client: PerpsClient) -> None:
        route = respx.put(f"{BASE}/margin/fcm/notional_risk_limit").mock(
            return_value=httpx.Response(200, json={})
        )
        req = UpdateFCMNotionalRiskLimitRequest(notional_value_risk_limit=Decimal("10.00"))
        perps_client.fcm.update_notional_risk_limit(request=req)
        assert json.loads(route.calls[0].request.content) == {
            "notional_value_risk_limit": "10.00",
        }

    def test_update_requires_args(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError, match="update_notional_risk_limit"):
            perps_client.fcm.update_notional_risk_limit()  # type: ignore[call-overload]

    @respx.mock
    def test_update_server_400(self, perps_client: PerpsClient) -> None:
        respx.put(f"{BASE}/margin/fcm/notional_risk_limit").mock(
            return_value=httpx.Response(400, json={"message": "above Kalshi ceiling"})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped validation error
            perps_client.fcm.update_notional_risk_limit(
                notional_value_risk_limit=Decimal("999999.0000")
            )

    def test_update_unauthenticated(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo(max_retries=0))
        with pytest.raises(AuthRequiredError):
            client.fcm.update_notional_risk_limit(notional_value_risk_limit=Decimal("1"))

    @respx.mock
    def test_delete(self, perps_client: PerpsClient) -> None:
        route = respx.delete(f"{BASE}/margin/fcm/notional_risk_limit").mock(
            return_value=httpx.Response(200, json={})
        )
        assert perps_client.fcm.delete_notional_risk_limit() is None
        assert route.called
        assert route.calls[0].request.content == b""

    @respx.mock
    def test_delete_server_401(self, perps_client: PerpsClient) -> None:
        respx.delete(f"{BASE}/margin/fcm/notional_risk_limit").mock(
            return_value=httpx.Response(401, json={"message": "unauthorized"})
        )
        with pytest.raises(Exception):  # noqa: B017 — mapped auth error
            perps_client.fcm.delete_notional_risk_limit()

    def test_delete_unauthenticated(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo(max_retries=0))
        with pytest.raises(AuthRequiredError):
            client.fcm.delete_notional_risk_limit()

    @respx.mock
    async def test_async_roundtrip(self, async_perps_client: AsyncPerpsClient) -> None:
        put = respx.put(f"{BASE}/margin/fcm/notional_risk_limit").mock(
            return_value=httpx.Response(200, json={})
        )
        delete = respx.delete(f"{BASE}/margin/fcm/notional_risk_limit").mock(
            return_value=httpx.Response(200, json={})
        )
        await async_perps_client.fcm.update_notional_risk_limit(
            notional_value_risk_limit=Decimal("2.00")
        )
        await async_perps_client.fcm.delete_notional_risk_limit()
        assert json.loads(put.calls[0].request.content) == {
            "notional_value_risk_limit": "2.00",
        }
        assert delete.called


_TRANSFER_ID = "6d1f0c5a-2b3e-4f7a-9c8d-0e1f2a3b4c5d"
_TRANSFER_PATH = f"{BASE}/margin/fcm/positions/transfers"
_SOURCE = "3f2a8c1e-5b7d-4e9a-8c6f-1d2b3a4e5f60_CUST123"
_TARGET = "9b8c7d6e-5f4a-4b3c-9d2e-1f0a9b8c7d6e_ERR1"


def _happy_kwargs() -> dict[str, object]:
    return {
        "source_subtrader_id": _SOURCE,
        "target_subtrader_id": _TARGET,
        "ticker": "KXBTCPERP",
        "side": "long",
        "count": "10",
        "price": "63000.00",
        "client_transfer_id": _TRANSFER_ID,
    }


def _happy_body() -> dict[str, object]:
    return {
        "source_subtrader_id": _SOURCE,
        "target_subtrader_id": _TARGET,
        "ticker": "KXBTCPERP",
        "side": "long",
        "count": "10",
        "price": "63000.00",
        "client_transfer_id": _TRANSFER_ID,
    }


class TestCreateMarginFCMPositionTransferRequest:
    def test_serializes(self) -> None:
        req = CreateMarginFCMPositionTransferRequest(
            source_subtrader_id=_SOURCE,
            target_subtrader_id=_TARGET,
            ticker="KXBTCPERP",
            side="long",
            count="10",
            price="63000.00",
            client_transfer_id=_TRANSFER_ID,
        )
        assert req.model_dump(exclude_none=True, by_alias=True, mode="json") == _happy_body()

    def test_serializes_decimal_count_and_price(self) -> None:
        req = CreateMarginFCMPositionTransferRequest(
            source_subtrader_id=_SOURCE,
            target_subtrader_id=_TARGET,
            ticker="KXBTCPERP",
            side="long",
            count=Decimal("10"),
            price=Decimal("63000.00"),
            client_transfer_id=_TRANSFER_ID,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body["count"] == "10"
        assert body["price"] == "63000.00"

    def test_market_id_omits_ticker(self) -> None:
        req = CreateMarginFCMPositionTransferRequest(
            source_subtrader_id=_SOURCE,
            target_subtrader_id=_TARGET,
            market_id="0a1b2c3d-4e5f-4a6b-8c9d-0e1f2a3b4c5d",
            side="short",
            count="5",
            price="4500.00",
            client_transfer_id=_TRANSFER_ID,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert "ticker" not in body
        assert body["market_id"] == "0a1b2c3d-4e5f-4a6b-8c9d-0e1f2a3b4c5d"
        assert body["side"] == "short"

    def test_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMPositionTransferRequest(  # type: ignore[call-arg]
                source_subtrader_id=_SOURCE,
                target_subtrader_id=_TARGET,
                ticker="KXBTCPERP",
                side="long",
                count="10",
                price="63000.00",
                client_transfer_id=_TRANSFER_ID,
                phantom=1,
            )

    def test_rejects_bad_side(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginFCMPositionTransferRequest(
                source_subtrader_id=_SOURCE,
                target_subtrader_id=_TARGET,
                ticker="KXBTCPERP",
                side="bid",  # type: ignore[arg-type]
                count="10",
                price="63000.00",
                client_transfer_id=_TRANSFER_ID,
            )


class TestFcmTransferPosition:
    @respx.mock
    def test_happy_path_sends_exact_body(self, perps_client: PerpsClient) -> None:
        route = respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(
                201, json={"position_transfer_id": "pt-1"}
            )
        )
        resp = perps_client.fcm.transfer_position(**_happy_kwargs())  # type: ignore[arg-type]
        assert isinstance(resp, CreateMarginFCMPositionTransferResponse)
        assert resp.position_transfer_id == "pt-1"
        assert route.calls[0].request.method == "POST"
        assert str(route.calls[0].request.url.path).endswith(
            "/margin/fcm/positions/transfers"
        )
        assert json.loads(route.calls[0].request.content) == _happy_body()

    @respx.mock
    def test_with_request_model(self, perps_client: PerpsClient) -> None:
        route = respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(201, json={"position_transfer_id": "pt-2"})
        )
        req = CreateMarginFCMPositionTransferRequest(
            source_subtrader_id=_SOURCE,
            target_subtrader_id=_TARGET,
            ticker="KXBTCPERP",
            side="long",
            count="10",
            price="63000.00",
            client_transfer_id=_TRANSFER_ID,
        )
        resp = perps_client.fcm.transfer_position(request=req)
        assert resp.position_transfer_id == "pt-2"
        assert json.loads(route.calls[0].request.content) == _happy_body()

    @respx.mock
    def test_market_id_instead_of_ticker(self, perps_client: PerpsClient) -> None:
        route = respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(201, json={"position_transfer_id": "pt-3"})
        )
        perps_client.fcm.transfer_position(
            source_subtrader_id=_SOURCE,
            target_subtrader_id=_TARGET,
            market_id="0a1b2c3d-4e5f-4a6b-8c9d-0e1f2a3b4c5d",
            side="short",
            count="5",
            price="4500.00",
            client_transfer_id=_TRANSFER_ID,
        )
        assert json.loads(route.calls[0].request.content) == {
            "source_subtrader_id": _SOURCE,
            "target_subtrader_id": _TARGET,
            "market_id": "0a1b2c3d-4e5f-4a6b-8c9d-0e1f2a3b4c5d",
            "side": "short",
            "count": "5",
            "price": "4500.00",
            "client_transfer_id": _TRANSFER_ID,
        }

    @respx.mock
    def test_decimal_count_and_price_serialize(self, perps_client: PerpsClient) -> None:
        route = respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(201, json={"position_transfer_id": "pt-4"})
        )
        perps_client.fcm.transfer_position(
            source_subtrader_id=_SOURCE,
            target_subtrader_id=_TARGET,
            ticker="KXBTCPERP",
            side="long",
            count=Decimal("10"),
            price=Decimal("63000.00"),
            client_transfer_id=UUID(_TRANSFER_ID),
        )
        body = json.loads(route.calls[0].request.content)
        assert body["count"] == "10"
        assert body["price"] == "63000.00"
        assert body["client_transfer_id"] == _TRANSFER_ID

    def test_requires_args(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError, match="transfer_position"):
            perps_client.fcm.transfer_position()  # type: ignore[call-overload]

    @respx.mock
    def test_409_maps_conflict(self, perps_client: PerpsClient) -> None:
        respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(
                409, json={"error": {"code": "transfer_already_applied"}}
            )
        )
        with pytest.raises(KalshiConflictError):
            perps_client.fcm.transfer_position(**_happy_kwargs())  # type: ignore[arg-type]

    @respx.mock
    def test_400_maps_validation(self, perps_client: PerpsClient) -> None:
        respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(400, json={"message": "not enabled"})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.fcm.transfer_position(**_happy_kwargs())  # type: ignore[arg-type]

    @respx.mock
    def test_not_retried_on_5xx(self, perps_client: PerpsClient) -> None:
        route = respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(503, json={"error": {"code": "unavailable"}})
        )
        with pytest.raises(KalshiServerError):
            perps_client.fcm.transfer_position(**_happy_kwargs())  # type: ignore[arg-type]
        assert route.call_count == 1

    def test_unauthenticated_raises(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo(max_retries=0))
        with pytest.raises(AuthRequiredError):
            client.fcm.transfer_position(**_happy_kwargs())  # type: ignore[arg-type]


class TestAsyncFcmTransferPosition:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path_sends_exact_body(
        self, async_perps_client: AsyncPerpsClient
    ) -> None:
        route = respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(
                201, json={"position_transfer_id": "pt-async"}
            )
        )
        resp = await async_perps_client.fcm.transfer_position(**_happy_kwargs())  # type: ignore[arg-type]
        assert resp.position_transfer_id == "pt-async"
        assert route.calls[0].request.method == "POST"
        assert json.loads(route.calls[0].request.content) == _happy_body()

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_retried_on_5xx(
        self, async_perps_client: AsyncPerpsClient
    ) -> None:
        route = respx.post(_TRANSFER_PATH).mock(
            return_value=httpx.Response(500, json={"error": {"code": "boom"}})
        )
        with pytest.raises(KalshiServerError):
            await async_perps_client.fcm.transfer_position(**_happy_kwargs())  # type: ignore[arg-type]
        assert route.call_count == 1
