"""Tests for kalshi.resources.subaccounts — multi-account resource."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.async_client import AsyncKalshiClient
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import DEMO_BASE_URL, DEMO_WS_URL, KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.models.subaccounts import (
    ApplySubaccountPositionTransferRequest,
    ApplySubaccountPositionTransferResponse,
    ApplySubaccountTransferRequest,
    CreateSubaccountRequest,
    CreateSubaccountResponse,
    GetSubaccountBalancesResponse,
    GetSubaccountNettingResponse,
    LockSubaccountForSettlementAdvanceRequest,
    LockSubaccountForSettlementAdvanceResponse,
    SubaccountBalance,
    SubaccountNettingConfig,
    SubaccountTransfer,
    UnlockSubaccountForSettlementAdvanceRequest,
    UpdateSubaccountNettingRequest,
)
from kalshi.resources.subaccounts import (
    AsyncSubaccountsResource,
    SubaccountsResource,
)

# Required settlement-advance fields on SubaccountBalance (OpenAPI 3.26.0 content).
_BALANCE_ADVANCE_FIELDS = {
    "voluntarily_locked": False,
    "settlement_advance": "0.0000",
}

_TEST_ADVANCE_STATE = "550e8400-e29b-41d4-a716-446655440099"


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def subaccounts(test_auth: KalshiAuth, config: KalshiConfig) -> SubaccountsResource:
    return SubaccountsResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_subaccounts(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncSubaccountsResource:
    return AsyncSubaccountsResource(AsyncTransport(test_auth, config))


@pytest.fixture
def client(test_auth: KalshiAuth) -> KalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, timeout=5.0, max_retries=0)
    return KalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def async_client(test_auth: KalshiAuth) -> AsyncKalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, timeout=5.0, max_retries=0)
    return AsyncKalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def unauth_subaccounts(config: KalshiConfig) -> SubaccountsResource:
    return SubaccountsResource(SyncTransport(None, config))


class TestSubaccountModels:
    def test_subaccount_balance_parses_dollar_decimal(self) -> None:
        bal = SubaccountBalance.model_validate(
            {
                "subaccount_number": 1,
                "exchange_index": 0,
                "balance": "12.3400",
                "updated_ts": 1_700_000_000,
                **_BALANCE_ADVANCE_FIELDS,
            }
        )
        assert bal.subaccount_number == 1
        assert bal.balance == Decimal("12.3400")
        assert bal.updated_ts == 1_700_000_000
        assert bal.voluntarily_locked is False
        assert bal.settlement_advance == Decimal("0.0000")
        assert bal.settlement_advance_state is None

    def test_subaccount_balance_settlement_advance_fields(self) -> None:
        state = "550e8400-e29b-41d4-a716-446655440099"
        bal = SubaccountBalance.model_validate(
            {
                "subaccount_number": 2,
                "exchange_index": 0,
                "balance": "1.00",
                "updated_ts": 1,
                "voluntarily_locked": True,
                "settlement_advance": "3.5000",
                "settlement_advance_state": state,
            }
        )
        assert bal.voluntarily_locked is True
        assert bal.settlement_advance == Decimal("3.5000")
        assert str(bal.settlement_advance_state) == state

    def test_subaccount_balance_requires_settlement_advance_fields(self) -> None:
        with pytest.raises(ValidationError):
            SubaccountBalance.model_validate(
                {
                    "subaccount_number": 0,
                    "exchange_index": 0,
                    "balance": "1.00",
                    "updated_ts": 1,
                    # voluntarily_locked / settlement_advance intentionally omitted
                }
            )

    def test_subaccount_transfer_parses(self) -> None:
        # Spec sync (2026-07-20/21): GET transfers is cash-only; transfer_type
        # and position fields are no longer on the wire schema.
        t = SubaccountTransfer.model_validate(
            {
                "transfer_id": "xfer-1",
                "from_subaccount": 0,
                "to_subaccount": 1,
                "amount_cents": 500,
                "created_ts": 1_700_000_000,
                "exchange_index": 0,
            }
        )
        assert t.transfer_id == "xfer-1"
        assert t.amount_cents == 500
        assert t.exchange_index == 0
        assert t.transfer_type is None
        assert t.market_ticker is None
        assert t.side is None

    def test_subaccount_transfer_soft_keeps_legacy_position_fields(self) -> None:
        # Lagging servers / cached payloads with the pre-removal shape still
        # parse: transfer_type and position-only fields are optional.
        t = SubaccountTransfer.model_validate(
            {
                "transfer_id": "xfer-2",
                "from_subaccount": 1,
                "to_subaccount": 2,
                "amount_cents": 0,
                "created_ts": 1_700_000_100,
                "exchange_index": 0,
                "transfer_type": "position",
                "market_ticker": "MKT-1",
                "side": "yes",
                "count": 10,
                "price": "0.55",
            }
        )
        assert t.transfer_type == "position"
        assert t.market_ticker == "MKT-1"
        assert t.side == "yes"
        assert t.count == 10
        assert t.price == Decimal("0.55")

    def test_subaccount_transfer_requires_exchange_index(self) -> None:
        # exchange_index remains spec-required. transfer_type was removed from
        # the wire schema and is optional on the SDK (defensive optional-ization).
        with pytest.raises(ValidationError):
            SubaccountTransfer.model_validate(
                {
                    "transfer_id": "xfer-3",
                    "from_subaccount": 0,
                    "to_subaccount": 1,
                    "amount_cents": 100,
                    "created_ts": 1_700_000_200,
                    # exchange_index intentionally omitted
                }
            )

    def test_subaccount_netting_config_parses(self) -> None:
        cfg = SubaccountNettingConfig.model_validate(
            {"subaccount_number": 2, "enabled": True, "exchange_index": 0},
        )
        assert cfg.subaccount_number == 2
        assert cfg.enabled is True
        assert cfg.exchange_index == 0

    def test_get_balances_response_wraps_list(self) -> None:
        resp = GetSubaccountBalancesResponse.model_validate(
            {
                "subaccount_balances": [
                    {
                        "subaccount_number": 0,
                        "exchange_index": 0,
                        "balance": "100.00",
                        "updated_ts": 1,
                        **_BALANCE_ADVANCE_FIELDS,
                    },
                ],
            },
        )
        assert len(resp.subaccount_balances) == 1
        assert resp.subaccount_balances[0].subaccount_number == 0

    def test_get_netting_response_wraps_list(self) -> None:
        resp = GetSubaccountNettingResponse.model_validate(
            {"netting_configs": [{"subaccount_number": 1, "enabled": False, "exchange_index": 0}]},
        )
        assert len(resp.netting_configs) == 1

    def test_create_subaccount_response(self) -> None:
        resp = CreateSubaccountResponse.model_validate({"subaccount_number": 3})
        assert resp.subaccount_number == 3


_TEST_XFER_ID = "550e8400-e29b-41d4-a716-446655440000"


class TestSubaccountRequestModels:
    def test_transfer_request_serializes(self) -> None:
        req = ApplySubaccountTransferRequest(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=0,
            to_subaccount=1,
            amount_cents=500,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "client_transfer_id": _TEST_XFER_ID,
            "from_subaccount": 0,
            "to_subaccount": 1,
            "amount_cents": 500,
        }

    def test_transfer_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(  # type: ignore[call-arg]
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=100,
                phantom=True,
            )

    def test_transfer_request_rejects_negative_subaccount(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=-1,
                to_subaccount=1,
                amount_cents=100,
            )

    def test_transfer_request_rejects_non_uuid_client_id(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(
                client_transfer_id="not-a-uuid",
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=100,
            )

    def test_transfer_request_rejects_zero_amount(self) -> None:
        # Spec treats positive integer cents; zero transfers are a bug signal.
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=0,
            )

    def test_transfer_request_accepts_subaccount_above_32(self) -> None:
        """Regression guard for #164: demo allocates subaccount numbers above 32.

        Spec describes ``1-32`` in prose but defines no JSON-schema maximum,
        and an integration test caught the SDK rejecting a server-assigned 41
        before the request could leave the client. The SDK validates only the
        lower bound (``ge=0``); the server is the source of truth on the upper.
        """
        req = ApplySubaccountTransferRequest(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=0,
            to_subaccount=41,
            amount_cents=100,
        )
        assert req.to_subaccount == 41
    def test_update_netting_request_serializes(self) -> None:
        req = UpdateSubaccountNettingRequest(subaccount_number=2, enabled=True)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"subaccount_number": 2, "enabled": True}

    def test_update_netting_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            UpdateSubaccountNettingRequest(  # type: ignore[call-arg]
                subaccount_number=0, enabled=True, phantom=1,
            )

    # ── #465 CreateSubaccountRequest (v3.23.0) ──
    def test_create_request_empty_serializes_to_empty_dict(self) -> None:
        assert CreateSubaccountRequest().model_dump(exclude_none=True) == {}

    def test_create_request_with_exchange_index(self) -> None:
        body = CreateSubaccountRequest(exchange_index=0).model_dump(exclude_none=True)
        assert body == {"exchange_index": 0}

    def test_create_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateSubaccountRequest(phantom=1)  # type: ignore[call-arg]

    def test_create_request_rejects_negative_exchange_index(self) -> None:
        with pytest.raises(ValidationError):
            CreateSubaccountRequest(exchange_index=-1)

    # ── #464 ApplySubaccountPositionTransferRequest (v3.23.0) ──
    def test_position_transfer_request_serializes(self) -> None:
        req = ApplySubaccountPositionTransferRequest(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=0,
            to_subaccount=1,
            market_ticker="MKT-1",
            side="yes",
            count=5,
            price=Decimal("0.50"),
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "client_transfer_id": _TEST_XFER_ID,
            "from_subaccount": 0,
            "to_subaccount": 1,
            "market_ticker": "MKT-1",
            "side": "yes",
            "count": 5,
            "price": "0.50",
        }

    def test_position_transfer_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountPositionTransferRequest(  # type: ignore[call-arg]
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                market_ticker="MKT-1",
                side="yes",
                count=5,
                price=Decimal("0.50"),
                phantom=1,
            )

    def test_position_transfer_request_rejects_bad_side(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountPositionTransferRequest(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                market_ticker="MKT-1",
                side="maybe",  # type: ignore[arg-type]
                count=5,
                price=Decimal("0.50"),
            )

    def test_position_transfer_request_rejects_zero_count(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountPositionTransferRequest(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                market_ticker="MKT-1",
                side="yes",
                count=0,
                price=Decimal("0.50"),
            )

    @pytest.mark.parametrize("bad_price", [Decimal("-0.01"), Decimal("0.123456")])
    def test_position_transfer_request_rejects_bad_price(self, bad_price: Decimal) -> None:
        # v3.24.0: `price` is OrderPrice (fixed-point dollars). Negatives and
        # sub-$0.0001-tick precision fail at construction; the upper bound is the
        # server's to enforce (mirrors CreateOrderRequest — no client-side cap).
        with pytest.raises(ValidationError):
            ApplySubaccountPositionTransferRequest(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                market_ticker="MKT-1",
                side="yes",
                count=5,
                price=bad_price,
            )

    # ── Settlement-advance lock / unlock request models (#486) ──
    def test_lock_settlement_advance_request_serializes(self) -> None:
        req = LockSubaccountForSettlementAdvanceRequest(subaccount_number=1)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"subaccount_number": 1}

    def test_lock_settlement_advance_request_with_exchange_index(self) -> None:
        req = LockSubaccountForSettlementAdvanceRequest(
            subaccount_number=0, exchange_index=0,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"subaccount_number": 0, "exchange_index": 0}

    def test_lock_settlement_advance_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            LockSubaccountForSettlementAdvanceRequest(  # type: ignore[call-arg]
                subaccount_number=0, phantom=1,
            )

    def test_unlock_settlement_advance_request_serializes(self) -> None:
        req = UnlockSubaccountForSettlementAdvanceRequest(
            subaccount_number=2, exchange_index=0,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"subaccount_number": 2, "exchange_index": 0}

    def test_unlock_settlement_advance_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            UnlockSubaccountForSettlementAdvanceRequest(  # type: ignore[call-arg]
                subaccount_number=0, phantom=1,
            )

    def test_lock_settlement_advance_response_parses_uuid(self) -> None:
        resp = LockSubaccountForSettlementAdvanceResponse.model_validate(
            {"settlement_advance_state": _TEST_ADVANCE_STATE},
        )
        assert str(resp.settlement_advance_state) == _TEST_ADVANCE_STATE


class TestSubaccountsCreate:
    @respx.mock
    def test_create_sends_empty_json_body(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        # Spec has no requestBody but demo rejects the POST without
        # Content-Type. SDK sends json={} (content == b"{}") to force the
        # header on httpx.
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts",
        ).mock(return_value=httpx.Response(201, json={"subaccount_number": 5}))
        resp = subaccounts.create()
        assert isinstance(resp, CreateSubaccountResponse)
        assert resp.subaccount_number == 5
        assert route.called
        assert route.calls[0].request.content == b"{}"

    @respx.mock
    def test_create_with_exchange_index_sends_body(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        # #465 (v3.23.0): create() now serializes an optional CreateSubaccountRequest.
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts",
        ).mock(return_value=httpx.Response(201, json={"subaccount_number": 6}))
        resp = subaccounts.create(exchange_index=0)
        assert resp.subaccount_number == 6
        assert json.loads(route.calls[0].request.content) == {"exchange_index": 0}

    @respx.mock
    def test_create_500_raises(self, subaccounts: SubaccountsResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts",
        ).mock(return_value=httpx.Response(500, json={"message": "boom"}))
        with pytest.raises(KalshiServerError):
            subaccounts.create()


class TestSubaccountsTransferPosition:
    @respx.mock
    def test_transfer_position_sends_body_and_returns_id(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/positions/transfer",
        ).mock(return_value=httpx.Response(200, json={"position_transfer_id": "pt-1"}))
        resp = subaccounts.transfer_position(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=0,
            to_subaccount=1,
            market_ticker="MKT-1",
            side="yes",
            count=10,
            price=Decimal("0.55"),
        )
        assert isinstance(resp, ApplySubaccountPositionTransferResponse)
        assert resp.position_transfer_id == "pt-1"
        assert json.loads(route.calls[0].request.content) == {
            "client_transfer_id": _TEST_XFER_ID,
            "from_subaccount": 0,
            "to_subaccount": 1,
            "market_ticker": "MKT-1",
            "side": "yes",
            "count": 10,
            "price": "0.55",
        }

    @respx.mock
    def test_transfer_position_with_request_model(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/positions/transfer",
        ).mock(return_value=httpx.Response(200, json={"position_transfer_id": "pt-2"}))
        req = ApplySubaccountPositionTransferRequest(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=1,
            to_subaccount=2,
            market_ticker="MKT-2",
            side="no",
            count=3,
            price=Decimal("0"),
        )
        resp = subaccounts.transfer_position(request=req)
        assert resp.position_transfer_id == "pt-2"
        assert route.called

    def test_transfer_position_requires_args(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(TypeError, match="transfer_position"):
            subaccounts.transfer_position(from_subaccount=0)

    def test_transfer_position_rejects_malformed_uuid(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(ValueError):
            subaccounts.transfer_position(
                client_transfer_id="not-a-uuid",
                from_subaccount=0,
                to_subaccount=1,
                market_ticker="MKT-1",
                side="yes",
                count=1,
                price=Decimal("0.01"),
            )

    @respx.mock
    def test_transfer_position_400_maps(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/positions/transfer",
        ).mock(return_value=httpx.Response(400, json={"message": "bad"}))
        with pytest.raises(KalshiValidationError):
            subaccounts.transfer_position(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                market_ticker="MKT-1",
                side="yes",
                count=1,
                price=Decimal("0.01"),
            )

    def test_transfer_position_unauthenticated_raises_before_http(
        self, config: KalshiConfig,
    ) -> None:
        client = SubaccountsResource(SyncTransport(None, config))
        with pytest.raises(AuthRequiredError):
            client.transfer_position(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                market_ticker="MKT-1",
                side="yes",
                count=1,
                price=Decimal("0.01"),
            )


class TestSubaccountsTransfer:
    @respx.mock
    def test_transfer_sends_body(self, subaccounts: SubaccountsResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfer",
        ).mock(return_value=httpx.Response(200, json={}))
        subaccounts.transfer(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=0,
            to_subaccount=1,
            amount_cents=250,
        )
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "client_transfer_id": _TEST_XFER_ID,
            "from_subaccount": 0,
            "to_subaccount": 1,
            "amount_cents": 250,
        }

    @respx.mock
    def test_transfer_400_maps(self, subaccounts: SubaccountsResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfer",
        ).mock(return_value=httpx.Response(400, json={"message": "insufficient"}))
        with pytest.raises(KalshiValidationError):
            subaccounts.transfer(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=999_999_999,
            )

    def test_transfer_rejects_malformed_uuid_at_resource_boundary(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        # transfer() accepts `UUID | str`; a malformed string must surface
        # as ValueError from UUID() at the call site, not a Pydantic error.
        with pytest.raises(ValueError):
            subaccounts.transfer(
                client_transfer_id="not-a-uuid",
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=100,
            )


class TestSubaccountsListBalances:
    @respx.mock
    def test_returns_balances(self, subaccounts: SubaccountsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/balances",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "subaccount_balances": [
                        {
                            "subaccount_number": 0,
                            "exchange_index": 0,
                            "balance": "10.00",
                            "updated_ts": 1,
                            **_BALANCE_ADVANCE_FIELDS,
                        },
                        {
                            "subaccount_number": 1,
                            "exchange_index": 0,
                            "balance": "5.00",
                            "updated_ts": 2,
                            **_BALANCE_ADVANCE_FIELDS,
                        },
                    ],
                },
            ),
        )
        resp = subaccounts.list_balances()
        assert isinstance(resp, GetSubaccountBalancesResponse)
        assert len(resp.subaccount_balances) == 2
        assert resp.subaccount_balances[0].balance == Decimal("10.00")
        assert resp.subaccount_balances[0].voluntarily_locked is False

    @respx.mock
    def test_empty_list(self, subaccounts: SubaccountsResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/balances",
        ).mock(
            return_value=httpx.Response(200, json={"subaccount_balances": []}),
        )
        resp = subaccounts.list_balances()
        assert resp.subaccount_balances == []


class TestSubaccountsListTransfers:
    @respx.mock
    def test_returns_paginated_transfers(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfers",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "transfers": [
                        {
                            "transfer_id": "t-1",
                            "from_subaccount": 0,
                            "to_subaccount": 1,
                            "amount_cents": 100,
                            "created_ts": 1,
                            "exchange_index": 0,
                        },
                    ],
                    "cursor": "next",
                },
            ),
        )
        page = subaccounts.list_transfers(limit=25)
        assert len(page.items) == 1
        assert page.cursor == "next"

    @respx.mock
    def test_list_all_auto_paginates(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfers",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "transfers": [
                            {
                                "transfer_id": "t-1",
                                "from_subaccount": 0,
                                "to_subaccount": 1,
                                "amount_cents": 100,
                                "created_ts": 1,
                                "exchange_index": 0,
                            },
                        ],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "transfers": [
                            {
                                "transfer_id": "t-2",
                                "from_subaccount": 1,
                                "to_subaccount": 0,
                                "amount_cents": 50,
                                "created_ts": 2,
                                "exchange_index": 0,
                            },
                        ],
                    },
                ),
            ],
        )
        items = list(subaccounts.list_all_transfers())
        assert [t.transfer_id for t in items] == ["t-1", "t-2"]


class TestSubaccountsNetting:
    @respx.mock
    def test_update_netting_sends_put(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/netting",
        ).mock(return_value=httpx.Response(200, json={}))
        subaccounts.update_netting(subaccount_number=2, enabled=True)
        body = json.loads(route.calls[0].request.content)
        assert body == {"subaccount_number": 2, "enabled": True}

    @respx.mock
    def test_update_netting_204_no_content(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        # _put now handles 204 cleanly (P3 fix landed upstream in this phase)
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/netting",
        ).mock(return_value=httpx.Response(204))
        subaccounts.update_netting(subaccount_number=0, enabled=False)
        assert route.called

    @respx.mock
    def test_get_netting_returns_configs(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/netting",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "netting_configs": [
                        {"subaccount_number": 0, "enabled": True, "exchange_index": 0},
                        {"subaccount_number": 1, "enabled": False, "exchange_index": 0},
                    ],
                },
            ),
        )
        resp = subaccounts.get_netting()
        assert isinstance(resp, GetSubaccountNettingResponse)
        assert len(resp.netting_configs) == 2

    @respx.mock
    def test_get_netting_500_raises(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/netting",
        ).mock(return_value=httpx.Response(500, json={"message": "boom"}))
        with pytest.raises(KalshiServerError):
            subaccounts.get_netting()


@pytest.mark.asyncio
class TestAsyncSubaccounts:
    async def test_create(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts",
        ).mock(return_value=httpx.Response(201, json={"subaccount_number": 7}))
        resp = await async_subaccounts.create()
        assert resp.subaccount_number == 7

    async def test_transfer(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfer",
        ).mock(return_value=httpx.Response(200, json={}))
        await async_subaccounts.transfer(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=0,
            to_subaccount=1,
            amount_cents=42,
        )
        body = json.loads(route.calls[0].request.content)
        assert body["amount_cents"] == 42

    async def test_transfer_position(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/positions/transfer",
        ).mock(return_value=httpx.Response(200, json={"position_transfer_id": "pt-async"}))
        resp = await async_subaccounts.transfer_position(
            client_transfer_id=_TEST_XFER_ID,
            from_subaccount=0,
            to_subaccount=1,
            market_ticker="MKT-1",
            side="no",
            count=4,
            price=Decimal("0.25"),
        )
        assert isinstance(resp, ApplySubaccountPositionTransferResponse)
        assert resp.position_transfer_id == "pt-async"
        body = json.loads(route.calls[0].request.content)
        assert body["side"] == "no"
        assert body["price"] == "0.25"

    async def test_list_balances(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/balances",
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "subaccount_balances": [
                        {
                            "subaccount_number": 0,
                            "exchange_index": 0,
                            "balance": "1.00",
                            "updated_ts": 1,
                            **_BALANCE_ADVANCE_FIELDS,
                        },
                    ],
                },
            ),
        )
        resp = await async_subaccounts.list_balances()
        assert len(resp.subaccount_balances) == 1

    async def test_list_transfers(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfers",
        ).mock(return_value=httpx.Response(200, json={"transfers": []}))
        page = await async_subaccounts.list_transfers()
        assert page.items == []

    async def test_list_all_transfers(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfers",
        ).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "transfers": [
                            {
                                "transfer_id": "t-1",
                                "from_subaccount": 0,
                                "to_subaccount": 1,
                                "amount_cents": 100,
                                "created_ts": 1,
                                "exchange_index": 0,
                            },
                        ],
                        "cursor": "p2",
                    },
                ),
                httpx.Response(200, json={"transfers": []}),
            ],
        )
        ids = [t.transfer_id async for t in async_subaccounts.list_all_transfers()]
        assert ids == ["t-1"]

    async def test_update_netting(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/netting",
        ).mock(return_value=httpx.Response(200, json={}))
        await async_subaccounts.update_netting(
            subaccount_number=1, enabled=True,
        )
        body = json.loads(route.calls[0].request.content)
        assert body == {"subaccount_number": 1, "enabled": True}

    async def test_get_netting(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        respx_mock.get(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/netting",
        ).mock(
            return_value=httpx.Response(200, json={"netting_configs": []}),
        )
        resp = await async_subaccounts.get_netting()
        assert resp.netting_configs == []

    async def test_lock_settlement_advance(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/"
            "settlement-advance-lock",
        ).mock(
            return_value=httpx.Response(
                200, json={"settlement_advance_state": _TEST_ADVANCE_STATE},
            ),
        )
        resp = await async_subaccounts.lock_settlement_advance(subaccount_number=1)
        assert str(resp.settlement_advance_state) == _TEST_ADVANCE_STATE
        assert json.loads(route.calls[0].request.content) == {"subaccount_number": 1}

    async def test_unlock_settlement_advance(
        self,
        async_subaccounts: AsyncSubaccountsResource,
        respx_mock: respx.MockRouter,
    ) -> None:
        route = respx_mock.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/"
            "settlement-advance-lock",
        ).mock(return_value=httpx.Response(200, json={}))
        result = await async_subaccounts.unlock_settlement_advance(subaccount_number=1)
        assert result is None
        assert json.loads(route.calls[0].request.content) == {"subaccount_number": 1}


class TestSubaccountsSettlementAdvance:
    @respx.mock
    def test_lock_settlement_advance_kwargs(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/"
            "settlement-advance-lock",
        ).mock(
            return_value=httpx.Response(
                200, json={"settlement_advance_state": _TEST_ADVANCE_STATE},
            ),
        )
        resp = subaccounts.lock_settlement_advance(
            subaccount_number=1, exchange_index=0,
        )
        assert isinstance(resp, LockSubaccountForSettlementAdvanceResponse)
        assert str(resp.settlement_advance_state) == _TEST_ADVANCE_STATE
        assert json.loads(route.calls[0].request.content) == {
            "subaccount_number": 1,
            "exchange_index": 0,
        }

    @respx.mock
    def test_lock_settlement_advance_request_model(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        route = respx.put(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/"
            "settlement-advance-lock",
        ).mock(
            return_value=httpx.Response(
                200, json={"settlement_advance_state": _TEST_ADVANCE_STATE},
            ),
        )
        req = LockSubaccountForSettlementAdvanceRequest(subaccount_number=0)
        resp = subaccounts.lock_settlement_advance(request=req)
        assert str(resp.settlement_advance_state) == _TEST_ADVANCE_STATE
        assert json.loads(route.calls[0].request.content) == {"subaccount_number": 0}

    def test_lock_settlement_advance_requires_subaccount(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(TypeError, match="subaccount_number"):
            subaccounts.lock_settlement_advance()

    def test_lock_settlement_advance_rejects_mixed_args(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        req = LockSubaccountForSettlementAdvanceRequest(subaccount_number=0)
        with pytest.raises(TypeError, match="either `request="):
            subaccounts.lock_settlement_advance(request=req, subaccount_number=1)

    @respx.mock
    def test_unlock_settlement_advance_kwargs(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/"
            "settlement-advance-lock",
        ).mock(return_value=httpx.Response(200, json={}))
        result = subaccounts.unlock_settlement_advance(subaccount_number=2)
        assert result is None
        assert json.loads(route.calls[0].request.content) == {"subaccount_number": 2}

    @respx.mock
    def test_unlock_settlement_advance_request_model(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/"
            "settlement-advance-lock",
        ).mock(return_value=httpx.Response(200, json={}))
        req = UnlockSubaccountForSettlementAdvanceRequest(
            subaccount_number=3, exchange_index=0,
        )
        result = subaccounts.unlock_settlement_advance(request=req)
        assert result is None
        assert json.loads(route.calls[0].request.content) == {
            "subaccount_number": 3,
            "exchange_index": 0,
        }

    def test_unlock_settlement_advance_requires_subaccount(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(TypeError, match="subaccount_number"):
            subaccounts.unlock_settlement_advance()


class TestSubaccountsAuthGuard:
    def test_create_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.create()

    def test_transfer_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.transfer(
                client_transfer_id=_TEST_XFER_ID,
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=1,
            )

    def test_list_balances_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.list_balances()

    def test_list_transfers_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.list_transfers()

    def test_list_all_transfers_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            list(unauth_subaccounts.list_all_transfers())

    def test_update_netting_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.update_netting(
                subaccount_number=0, enabled=True,
            )

    def test_get_netting_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.get_netting()

    def test_lock_settlement_advance_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.lock_settlement_advance(subaccount_number=0)

    def test_unlock_settlement_advance_requires_auth(
        self, unauth_subaccounts: SubaccountsResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_subaccounts.unlock_settlement_advance(subaccount_number=0)


class TestClientWiring:
    def test_sync_client_exposes_subaccounts(
        self, client: KalshiClient,
    ) -> None:
        assert isinstance(client.subaccounts, SubaccountsResource)

    def test_async_client_exposes_subaccounts(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        assert isinstance(async_client.subaccounts, AsyncSubaccountsResource)
