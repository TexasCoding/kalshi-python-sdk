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
from kalshi.config import DEMO_BASE_URL, KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.models.subaccounts import (
    ApplySubaccountTransferRequest,
    CreateSubaccountResponse,
    GetSubaccountBalancesResponse,
    GetSubaccountNettingResponse,
    SubaccountBalance,
    SubaccountNettingConfig,
    SubaccountTransfer,
    UpdateSubaccountNettingRequest,
)
from kalshi.resources.subaccounts import (
    AsyncSubaccountsResource,
    SubaccountsResource,
)


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
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return KalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def async_client(test_auth: KalshiAuth) -> AsyncKalshiClient:
    cfg = KalshiConfig(base_url=DEMO_BASE_URL, timeout=5.0, max_retries=0)
    return AsyncKalshiClient(auth=test_auth, config=cfg)


@pytest.fixture
def unauth_subaccounts(config: KalshiConfig) -> SubaccountsResource:
    return SubaccountsResource(SyncTransport(None, config))


class TestSubaccountModels:
    def test_subaccount_balance_parses_dollar_decimal(self) -> None:
        bal = SubaccountBalance.model_validate(
            {
                "subaccount_number": 1,
                "balance": "12.3400",
                "updated_ts": 1_700_000_000,
            }
        )
        assert bal.subaccount_number == 1
        assert bal.balance == Decimal("12.3400")
        assert bal.updated_ts == 1_700_000_000

    def test_subaccount_transfer_parses(self) -> None:
        t = SubaccountTransfer.model_validate(
            {
                "transfer_id": "xfer-1",
                "from_subaccount": 0,
                "to_subaccount": 1,
                "amount_cents": 500,
                "created_ts": 1_700_000_000,
            }
        )
        assert t.transfer_id == "xfer-1"
        assert t.amount_cents == 500

    def test_subaccount_netting_config_parses(self) -> None:
        cfg = SubaccountNettingConfig.model_validate(
            {"subaccount_number": 2, "enabled": True},
        )
        assert cfg.subaccount_number == 2
        assert cfg.enabled is True

    def test_get_balances_response_wraps_list(self) -> None:
        resp = GetSubaccountBalancesResponse.model_validate(
            {
                "subaccount_balances": [
                    {
                        "subaccount_number": 0,
                        "balance": "100.00",
                        "updated_ts": 1,
                    },
                ],
            },
        )
        assert len(resp.subaccount_balances) == 1
        assert resp.subaccount_balances[0].subaccount_number == 0

    def test_get_netting_response_wraps_list(self) -> None:
        resp = GetSubaccountNettingResponse.model_validate(
            {"netting_configs": [{"subaccount_number": 1, "enabled": False}]},
        )
        assert len(resp.netting_configs) == 1

    def test_create_subaccount_response(self) -> None:
        resp = CreateSubaccountResponse.model_validate({"subaccount_number": 3})
        assert resp.subaccount_number == 3


class TestSubaccountRequestModels:
    def test_transfer_request_serializes(self) -> None:
        req = ApplySubaccountTransferRequest(
            client_transfer_id="client-abc",
            from_subaccount=0,
            to_subaccount=1,
            amount_cents=500,
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "client_transfer_id": "client-abc",
            "from_subaccount": 0,
            "to_subaccount": 1,
            "amount_cents": 500,
        }

    def test_transfer_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(  # type: ignore[call-arg]
                client_transfer_id="x",
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=100,
                phantom=True,
            )

    def test_transfer_request_rejects_negative_subaccount(self) -> None:
        with pytest.raises(ValidationError):
            ApplySubaccountTransferRequest(
                client_transfer_id="x",
                from_subaccount=-1,
                to_subaccount=1,
                amount_cents=100,
            )

    def test_update_netting_request_serializes(self) -> None:
        req = UpdateSubaccountNettingRequest(subaccount_number=2, enabled=True)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"subaccount_number": 2, "enabled": True}

    def test_update_netting_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            UpdateSubaccountNettingRequest(  # type: ignore[call-arg]
                subaccount_number=0, enabled=True, phantom=1,
            )


class TestSubaccountsCreate:
    @respx.mock
    def test_create_sends_empty_body(
        self, subaccounts: SubaccountsResource,
    ) -> None:
        # Spec has no requestBody — POST with no json arg.
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts",
        ).mock(return_value=httpx.Response(201, json={"subaccount_number": 5}))
        resp = subaccounts.create()
        assert isinstance(resp, CreateSubaccountResponse)
        assert resp.subaccount_number == 5
        assert route.called

    @respx.mock
    def test_create_500_raises(self, subaccounts: SubaccountsResource) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts",
        ).mock(return_value=httpx.Response(500, json={"message": "boom"}))
        with pytest.raises(KalshiServerError):
            subaccounts.create()


class TestSubaccountsTransfer:
    @respx.mock
    def test_transfer_sends_body(self, subaccounts: SubaccountsResource) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/portfolio/subaccounts/transfer",
        ).mock(return_value=httpx.Response(200, json={}))
        subaccounts.transfer(
            client_transfer_id="client-1",
            from_subaccount=0,
            to_subaccount=1,
            amount_cents=250,
        )
        body = json.loads(route.calls[0].request.content)
        assert body == {
            "client_transfer_id": "client-1",
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
                client_transfer_id="client-1",
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=999_999_999,
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
                            "balance": "10.00",
                            "updated_ts": 1,
                        },
                        {
                            "subaccount_number": 1,
                            "balance": "5.00",
                            "updated_ts": 2,
                        },
                    ],
                },
            ),
        )
        resp = subaccounts.list_balances()
        assert isinstance(resp, GetSubaccountBalancesResponse)
        assert len(resp.subaccount_balances) == 2
        assert resp.subaccount_balances[0].balance == Decimal("10.00")

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
                        {"subaccount_number": 0, "enabled": True},
                        {"subaccount_number": 1, "enabled": False},
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
            client_transfer_id="c-async",
            from_subaccount=0,
            to_subaccount=1,
            amount_cents=42,
        )
        body = json.loads(route.calls[0].request.content)
        assert body["amount_cents"] == 42

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
                            "balance": "1.00",
                            "updated_ts": 1,
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
                client_transfer_id="x",
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


class TestClientWiring:
    def test_sync_client_exposes_subaccounts(
        self, client: KalshiClient,
    ) -> None:
        assert isinstance(client.subaccounts, SubaccountsResource)

    def test_async_client_exposes_subaccounts(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        assert isinstance(async_client.subaccounts, AsyncSubaccountsResource)
