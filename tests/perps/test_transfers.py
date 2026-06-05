"""Tests for the perps transfers & subaccounts resource (#396)."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.auth import KalshiAuth
from kalshi.errors import AuthRequiredError, KalshiAuthError, KalshiValidationError
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.transfers import (
    ApplySubaccountTransferRequest,
    CreateSubaccountResponse,
    IntraExchangeInstanceTransferRequest,
    IntraExchangeInstanceTransferResponse,
)

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"
_XFER_ID = "550e8400-e29b-41d4-a716-446655440000"


# ── models ────────────────────────────────────────────────────────────────


class TestModels:
    def test_instance_request_serializes(self) -> None:
        req = IntraExchangeInstanceTransferRequest(
            source="event_contract", destination="margined", amount=100
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "source": "event_contract",
            "destination": "margined",
            "amount": 100,
            "source_exchange_shard": 0,
            "destination_exchange_shard": 0,
        }

    def test_instance_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            IntraExchangeInstanceTransferRequest(  # type: ignore[call-arg]
                source="event_contract", destination="margined", amount=1, phantom=True
            )

    def test_instance_request_rejects_nonpositive_amount(self) -> None:
        with pytest.raises(ValidationError):
            IntraExchangeInstanceTransferRequest(
                source="event_contract", destination="margined", amount=0
            )

    def test_instance_request_rejects_negative_shard(self) -> None:
        with pytest.raises(ValidationError):
            IntraExchangeInstanceTransferRequest(
                source="event_contract",
                destination="margined",
                amount=1,
                source_exchange_shard=-1,
            )

    def test_instance_request_rejects_bad_instance(self) -> None:
        with pytest.raises(ValidationError):
            IntraExchangeInstanceTransferRequest(
                source="nope",  # type: ignore[arg-type]
                destination="margined",
                amount=1,
            )

    def test_subaccount_request_serializes(self) -> None:
        req = ApplySubaccountTransferRequest(
            client_transfer_id=_XFER_ID, from_subaccount=0, to_subaccount=3, amount_cents=500
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "client_transfer_id": _XFER_ID,
            "from_subaccount": 0,
            "to_subaccount": 3,
            "amount_cents": 500,
        }

    def test_subaccount_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(  # type: ignore[call-arg]
                client_transfer_id=_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=1,
                phantom=True,
            )

    def test_subaccount_request_rejects_negative_subaccount(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(
                client_transfer_id=_XFER_ID, from_subaccount=-1, to_subaccount=1, amount_cents=1
            )

    def test_subaccount_request_rejects_zero_amount(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(
                client_transfer_id=_XFER_ID, from_subaccount=0, to_subaccount=1, amount_cents=0
            )

    def test_subaccount_request_accepts_above_32(self) -> None:
        req = ApplySubaccountTransferRequest(
            client_transfer_id=_XFER_ID, from_subaccount=0, to_subaccount=41, amount_cents=1
        )
        assert req.to_subaccount == 41

    def test_instance_response_parses(self) -> None:
        resp = IntraExchangeInstanceTransferResponse.model_validate(
            {"transfer_id": "abc", "extra_field": 1}
        )
        assert resp.transfer_id == "abc"

    def test_create_subaccount_response_parses(self) -> None:
        resp = CreateSubaccountResponse.model_validate({"subaccount_number": 5})
        assert resp.subaccount_number == 5


# ── transfer_instance ───────────────────────────────────────────────────────


class TestTransferInstance:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(200, json={"transfer_id": "abc"})
        )
        resp = perps_client.transfers.transfer_instance(
            source="event_contract", destination="margined", amount=100
        )
        assert isinstance(resp, IntraExchangeInstanceTransferResponse)
        assert resp.transfer_id == "abc"
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "source": "event_contract",
            "destination": "margined",
            "amount": 100,
            "source_exchange_shard": 0,
            "destination_exchange_shard": 0,
        }

    @respx.mock
    def test_request_object_overload_identical_body(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(200, json={"transfer_id": "abc"})
        )
        req = IntraExchangeInstanceTransferRequest(
            source="event_contract", destination="margined", amount=100
        )
        perps_client.transfers.transfer_instance(request=req)
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "source": "event_contract",
            "destination": "margined",
            "amount": 100,
            "source_exchange_shard": 0,
            "destination_exchange_shard": 0,
        }

    @respx.mock
    def test_403_not_available_maps(self, perps_client: PerpsClient) -> None:
        # Spec: endpoint "currently not available" — 403 maps to KalshiAuthError.
        respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(403, json={"error": {"code": "forbidden"}})
        )
        with pytest.raises(KalshiAuthError):
            perps_client.transfers.transfer_instance(
                source="event_contract", destination="margined", amount=1
            )

    @respx.mock
    def test_400_maps(self, perps_client: PerpsClient) -> None:
        respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(400, json={"message": "bad"})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.transfers.transfer_instance(
                source="event_contract", destination="margined", amount=1
            )

    @respx.mock
    def test_not_retried(self, test_auth: KalshiAuth) -> None:
        # POST is never retried even with a retryable 503 and max_retries set.
        route = respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(503, json={"message": "down"})
        )
        client = PerpsClient(config=PerpsConfig.demo(max_retries=5), auth=test_auth)
        with pytest.raises(Exception):  # noqa: B017 — mapped 503 server error
            client.transfers.transfer_instance(
                source="event_contract", destination="margined", amount=1
            )
        assert route.call_count == 1
        client.close()

    @respx.mock
    def test_edge_request_and_kwargs_mutually_exclusive(self, perps_client: PerpsClient) -> None:
        req = IntraExchangeInstanceTransferRequest(
            source="event_contract", destination="margined", amount=1
        )
        with pytest.raises(TypeError):
            perps_client.transfers.transfer_instance(request=req, amount=2)  # type: ignore[call-overload]

    def test_edge_missing_required_kwargs(self, perps_client: PerpsClient) -> None:
        with pytest.raises(TypeError):
            perps_client.transfers.transfer_instance()  # type: ignore[call-overload]

    def test_edge_nonpositive_amount_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValidationError):
            perps_client.transfers.transfer_instance(
                source="event_contract", destination="margined", amount=0
            )

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(200, json={"transfer_id": "x"})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.transfers.transfer_instance(
                source="event_contract", destination="margined", amount=1
            )
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(200, json={"transfer_id": "zzz"})
        )
        resp = await async_perps_client.transfers.transfer_instance(
            source="margined", destination="event_contract", amount=42
        )
        assert resp.transfer_id == "zzz"
        body = json.loads(route.calls[0].request.content)
        assert body["amount"] == 42
        await async_perps_client.close()

    @respx.mock
    async def test_async_unauth_raises_before_http(self) -> None:
        route = respx.post(f"{BASE}/portfolio/intra_exchange_instance_transfer").mock(
            return_value=httpx.Response(200, json={"transfer_id": "x"})
        )
        client = AsyncPerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            await client.transfers.transfer_instance(
                source="event_contract", destination="margined", amount=1
            )
        assert not route.called
        await client.close()


# ── create_subaccount ───────────────────────────────────────────────────────


class TestCreateSubaccount:
    @respx.mock
    def test_happy(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/margin/subaccounts").mock(
            return_value=httpx.Response(201, json={"subaccount_number": 5})
        )
        resp = perps_client.transfers.create_subaccount()
        assert isinstance(resp, CreateSubaccountResponse)
        assert resp.subaccount_number == 5
        assert route.calls[0].request.content == b"{}"
        assert route.calls[0].request.headers["content-type"] == "application/json"

    @respx.mock
    def test_401_maps(self, perps_client: PerpsClient) -> None:
        respx.post(f"{BASE}/portfolio/margin/subaccounts").mock(
            return_value=httpx.Response(401, json={"error": {"code": "unauthorized"}})
        )
        with pytest.raises(KalshiAuthError):
            perps_client.transfers.create_subaccount()

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.post(f"{BASE}/portfolio/margin/subaccounts").mock(
            return_value=httpx.Response(201, json={"subaccount_number": 1})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.transfers.create_subaccount()
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        respx.post(f"{BASE}/portfolio/margin/subaccounts").mock(
            return_value=httpx.Response(201, json={"subaccount_number": 7})
        )
        resp = await async_perps_client.transfers.create_subaccount()
        assert resp.subaccount_number == 7
        await async_perps_client.close()


# ── transfer_subaccount ──────────────────────────────────────────────────────


class TestTransferSubaccount:
    @respx.mock
    def test_happy_returns_none(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/margin/subaccounts/transfer").mock(
            return_value=httpx.Response(200, json={})
        )
        result = perps_client.transfers.transfer_subaccount(
            client_transfer_id=_XFER_ID, from_subaccount=0, to_subaccount=3, amount_cents=500
        )
        assert result is None
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "client_transfer_id": _XFER_ID,
            "from_subaccount": 0,
            "to_subaccount": 3,
            "amount_cents": 500,
        }

    @respx.mock
    def test_accepts_uuid_and_str(self, perps_client: PerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/margin/subaccounts/transfer").mock(
            return_value=httpx.Response(200, json={})
        )
        perps_client.transfers.transfer_subaccount(
            client_transfer_id=UUID(_XFER_ID),
            from_subaccount=1,
            to_subaccount=2,
            amount_cents=10,
        )
        body = json.loads(route.calls[0].request.content)
        assert body["client_transfer_id"] == _XFER_ID

    def test_malformed_uuid_raises_before_http(self, perps_client: PerpsClient) -> None:
        # Coercion happens before the HTTP call; malformed str → ValueError.
        with pytest.raises(ValueError):
            perps_client.transfers.transfer_subaccount(
                client_transfer_id="not-a-uuid",
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=1,
            )

    @respx.mock
    def test_400_maps(self, perps_client: PerpsClient) -> None:
        respx.post(f"{BASE}/portfolio/margin/subaccounts/transfer").mock(
            return_value=httpx.Response(400, json={"message": "insufficient"})
        )
        with pytest.raises(KalshiValidationError):
            perps_client.transfers.transfer_subaccount(
                client_transfer_id=_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=999_999_999,
            )

    def test_edge_zero_amount_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValidationError):
            perps_client.transfers.transfer_subaccount(
                client_transfer_id=_XFER_ID, from_subaccount=0, to_subaccount=1, amount_cents=0
            )

    def test_edge_negative_subaccount_raises(self, perps_client: PerpsClient) -> None:
        with pytest.raises(ValidationError):
            perps_client.transfers.transfer_subaccount(
                client_transfer_id=_XFER_ID, from_subaccount=-1, to_subaccount=1, amount_cents=1
            )

    def test_edge_forbids_phantom_key(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(
                **{  # type: ignore[arg-type]
                    "client_transfer_id": _XFER_ID,
                    "from_subaccount": 0,
                    "to_subaccount": 1,
                    "amount_cents": 1,
                    "phantom": True,
                }
            )

    @respx.mock
    def test_unauthenticated_raises_before_http(self) -> None:
        route = respx.post(f"{BASE}/portfolio/margin/subaccounts/transfer").mock(
            return_value=httpx.Response(200, json={})
        )
        client = PerpsClient(config=PerpsConfig.demo())
        with pytest.raises(AuthRequiredError):
            client.transfers.transfer_subaccount(
                client_transfer_id=_XFER_ID, from_subaccount=0, to_subaccount=1, amount_cents=1
            )
        assert not route.called
        client.close()

    @respx.mock
    async def test_async_happy(self, async_perps_client: AsyncPerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/margin/subaccounts/transfer").mock(
            return_value=httpx.Response(200, json={})
        )
        result = await async_perps_client.transfers.transfer_subaccount(
            client_transfer_id=_XFER_ID, from_subaccount=0, to_subaccount=1, amount_cents=42
        )
        assert result is None
        body = json.loads(route.calls[0].request.content)
        assert body["amount_cents"] == 42
        await async_perps_client.close()

    @respx.mock
    async def test_async_request_object(self, async_perps_client: AsyncPerpsClient) -> None:
        route = respx.post(f"{BASE}/portfolio/margin/subaccounts/transfer").mock(
            return_value=httpx.Response(200, json={})
        )
        req = ApplySubaccountTransferRequest(
            client_transfer_id=_XFER_ID, from_subaccount=2, to_subaccount=0, amount_cents=7
        )
        await async_perps_client.transfers.transfer_subaccount(request=req)
        body = json.loads(route.calls[0].request.content)
        assert body["from_subaccount"] == 2
        await async_perps_client.close()
