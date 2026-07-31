"""Tests for perps FCM create_subtrader (POST /margin/fcm/subtraders)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import AuthRequiredError
from kalshi.perps import PerpsClient, PerpsConfig
from kalshi.perps.models.fcm import (
    CreateMarginFCMSubtraderRequest,
    CreateMarginFCMSubtraderResponse,
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
