"""Integration tests for SubaccountsResource — multi-account workflows on demo.

Endpoint feasibility (audit 2026-04-18):
  demo-supported: create, transfer, list_balances, list_transfers,
                  update_netting
  demo-broken:    GET /portfolio/subaccounts/netting — demo returns 500
                  ``users/internal_server_error`` regardless of input.
                  Marked integration_real_api_only.

POST /portfolio/subaccounts creates a persistent subaccount on demo with
no DELETE endpoint available — every run permanently consumes one
subaccount slot. Acceptable per maintainer guidance; use a session-scoped
fixture so we only create one per test run.
"""

from __future__ import annotations

import logging
import uuid

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiError, KalshiValidationError
from kalshi.models.common import Page
from kalshi.models.subaccounts import (
    CreateSubaccountResponse,
    GetSubaccountBalancesResponse,
    SubaccountBalance,
    SubaccountTransfer,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

logger = logging.getLogger(__name__)

register(
    "SubaccountsResource",
    [
        "create",
        "get_netting",
        "list_all_transfers",
        "list_balances",
        "list_transfers",
        "transfer",
        "update_netting",
    ],
)


@pytest.fixture(scope="session")
def ephemeral_subaccount(sync_client: KalshiClient) -> int:
    """Create one subaccount for the entire test session.

    POST /portfolio/subaccounts has no DELETE counterpart and creates a
    permanent subaccount on demo. Session-scoped caching minimizes the
    number of orphans the suite leaves behind to one per run.
    """
    try:
        resp = sync_client.subaccounts.create()
    except KalshiValidationError as e:
        pytest.skip(f"demo refused create subaccount: {e}")
    logger.info("Created demo subaccount %s for test run", resp.subaccount_number)
    return resp.subaccount_number


@pytest.mark.integration
class TestSubaccountsSync:
    def test_create_returns_subaccount_number(
        self, ephemeral_subaccount: int,
    ) -> None:
        # Fixture-driven — asserts that the session create succeeded.
        assert isinstance(ephemeral_subaccount, int)
        assert ephemeral_subaccount >= 1

    def test_list_balances(self, sync_client: KalshiClient) -> None:
        resp = sync_client.subaccounts.list_balances()
        assert isinstance(resp, GetSubaccountBalancesResponse)
        # Primary (subaccount 0) always exists for an auth'd user.
        assert any(
            b.subaccount_number == 0 for b in resp.subaccount_balances
        ), "primary subaccount (number=0) not in balances response"
        for b in resp.subaccount_balances:
            assert isinstance(b, SubaccountBalance)
            assert_model_fields(b)

    def test_list_balances_reflects_ephemeral_subaccount(
        self,
        sync_client: KalshiClient,
        ephemeral_subaccount: int,
    ) -> None:
        # After create, the new subaccount number should be listable.
        resp = sync_client.subaccounts.list_balances()
        nums = {b.subaccount_number for b in resp.subaccount_balances}
        assert ephemeral_subaccount in nums, (
            f"subaccount {ephemeral_subaccount} not present in balances "
            f"(got {sorted(nums)})"
        )

    def test_list_transfers(self, sync_client: KalshiClient) -> None:
        page = sync_client.subaccounts.list_transfers(limit=10)
        assert isinstance(page, Page)
        for t in page.items:
            assert isinstance(t, SubaccountTransfer)
            assert_model_fields(t)

    def test_list_all_transfers(self, sync_client: KalshiClient) -> None:
        for i, t in enumerate(
            sync_client.subaccounts.list_all_transfers(limit=10),
        ):
            assert isinstance(t, SubaccountTransfer)
            if i >= 4:
                break

    def test_transfer_between_subaccounts(
        self,
        sync_client: KalshiClient,
        ephemeral_subaccount: int,
        demo_balance_cents: int,
    ) -> None:
        # Move 1 cent from primary to subaccount. Requires at least 1 cent
        # in primary.
        if demo_balance_cents < 1:
            pytest.skip(f"demo balance {demo_balance_cents}c below 1c threshold")
        client_xfer_id = str(uuid.uuid4())
        sync_client.subaccounts.transfer(
            client_transfer_id=client_xfer_id,
            from_subaccount=0,
            to_subaccount=ephemeral_subaccount,
            amount_cents=1,
        )

    def test_update_netting_primary_idempotent(
        self, sync_client: KalshiClient,
    ) -> None:
        # Flip primary (subaccount 0) netting off then back on. Endpoint
        # returns success on both transitions so no state check needed.
        sync_client.subaccounts.update_netting(
            subaccount_number=0, enabled=False,
        )
        sync_client.subaccounts.update_netting(
            subaccount_number=0, enabled=True,
        )

    def test_transfer_rejects_invalid_amount(
        self, sync_client: KalshiClient,
    ) -> None:
        # Negative amount should reject at the SDK model (ge=0 on amount_cents).
        # SDK boundary rejects before any network call — does not need an
        # actual subaccount, which keeps the test independent of fixture
        # state on demo-side create failures.
        with pytest.raises(ValueError):
            sync_client.subaccounts.transfer(
                client_transfer_id=str(uuid.uuid4()),
                from_subaccount=0,
                to_subaccount=1,
                amount_cents=-1,
            )


@pytest.mark.integration
@pytest.mark.integration_real_api_only
class TestSubaccountsRealApiOnly:
    """Endpoints demo cannot service.

    Per audit 2026-04-18: GET /portfolio/subaccounts/netting returns 500
    ``{service: "users", code: "internal_server_error"}`` on demo
    regardless of input. The endpoint is expected to work against the
    real Kalshi API.
    """

    def test_get_netting(self, sync_client: KalshiClient) -> None:
        resp = sync_client.subaccounts.get_netting()
        # Primary netting config always exists for authenticated users.
        primaries = [c for c in resp.netting_configs if c.subaccount_number == 0]
        assert primaries, "primary netting config absent"


@pytest.mark.integration
class TestSubaccountsAsync:
    @pytest.mark.asyncio
    async def test_list_balances(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        resp = await async_client.subaccounts.list_balances()
        assert isinstance(resp, GetSubaccountBalancesResponse)
        assert any(b.subaccount_number == 0 for b in resp.subaccount_balances)

    @pytest.mark.asyncio
    async def test_list_transfers(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        page = await async_client.subaccounts.list_transfers(limit=10)
        assert isinstance(page, Page)

    @pytest.mark.asyncio
    async def test_list_all_transfers(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        i = 0
        async for t in async_client.subaccounts.list_all_transfers(limit=10):
            assert isinstance(t, SubaccountTransfer)
            if i >= 4:
                break
            i += 1

    @pytest.mark.asyncio
    async def test_create(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        # Every call creates a real subaccount — acceptable orphan per
        # maintainer guidance. Uses its own subaccount, not session-scoped.
        try:
            resp = await async_client.subaccounts.create()
        except KalshiError as e:
            pytest.skip(f"demo refused async create subaccount: {e}")
        assert isinstance(resp, CreateSubaccountResponse)
        assert resp.subaccount_number >= 1

    @pytest.mark.asyncio
    async def test_update_netting_primary_idempotent(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        await async_client.subaccounts.update_netting(
            subaccount_number=0, enabled=False,
        )
        await async_client.subaccounts.update_netting(
            subaccount_number=0, enabled=True,
        )
