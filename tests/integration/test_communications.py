"""Integration tests for CommunicationsResource — RFQ + Quote lifecycle on demo.

Endpoint feasibility (audit 2026-04-18):
  demo-supported: get_id, list_rfqs, create_rfq, get_rfq, delete_rfq,
                  list_quotes (for own RFQs), create_quote, get_quote,
                  delete_quote, accept_quote, confirm_quote
  auth-gated:     GET /communications/quotes without an rfq_id filter —
                  the probe hit 403 with no params. The demo account can
                  list quotes bound to its own RFQs (rfq_id filter), so the
                  unfiltered list_quotes variant is marked
                  integration_real_api_only.

RFQ workflows require an open market; fixtures skip the test if none
are discoverable on demo. Quote-creation workflow requires that the demo
account can respond to its own RFQs — if the server rejects a self-quote
(has happened on previous Kalshi demo deploys), the quote-lifecycle tests
skip rather than fail.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator

import pytest

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import (
    KalshiAuthError,
    KalshiError,
    KalshiValidationError,
)
from kalshi.models.common import Page
from kalshi.models.communications import (
    RFQ,
    CreateRFQResponse,
    GetCommunicationsIDResponse,
    GetRFQResponse,
    Quote,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

logger = logging.getLogger(__name__)

register(
    "CommunicationsResource",
    [
        "accept_quote",
        "confirm_quote",
        "create_quote",
        "create_rfq",
        "delete_quote",
        "delete_rfq",
        "get_id",
        "get_quote",
        "get_rfq",
        "list_all_quotes",
        "list_all_rfqs",
        "list_quotes",
        "list_rfqs",
    ],
)


@pytest.fixture
def ephemeral_rfq(
    sync_client: KalshiClient, demo_market_ticker: str,
) -> Iterator[str]:
    """Create an RFQ for the test and clean it up afterward.

    Skips the test if the demo server refuses the RFQ creation (market
    may be closed for RFQ, or demo account lacks OTC permission).
    """
    try:
        resp = sync_client.communications.create_rfq(
            market_ticker=demo_market_ticker,
            rest_remainder=False,
            contracts=1,
        )
    except (KalshiValidationError, KalshiAuthError) as e:
        pytest.skip(f"demo refused create_rfq on {demo_market_ticker}: {e}")
    rfq_id = resp.id
    try:
        yield rfq_id
    finally:
        try:
            sync_client.communications.delete_rfq(rfq_id)
        except Exception:
            logger.warning("cleanup: failed to delete rfq %s", rfq_id)


@pytest.mark.integration
class TestCommunicationsSync:
    def test_get_id(self, sync_client: KalshiClient) -> None:
        resp = sync_client.communications.get_id()
        assert isinstance(resp, GetCommunicationsIDResponse)
        assert resp.communications_id
        assert_model_fields(resp)

    def test_list_rfqs(self, sync_client: KalshiClient) -> None:
        page = sync_client.communications.list_rfqs(limit=10)
        assert isinstance(page, Page)
        for rfq in page.items:
            assert isinstance(rfq, RFQ)
            assert_model_fields(rfq)

    def test_list_all_rfqs(self, sync_client: KalshiClient) -> None:
        # Bounded walk — stop after 5 items to avoid unbounded pagination.
        for i, rfq in enumerate(
            sync_client.communications.list_all_rfqs(limit=10),
        ):
            assert isinstance(rfq, RFQ)
            if i >= 4:
                break

    def test_create_and_get_rfq(
        self, sync_client: KalshiClient, ephemeral_rfq: str,
    ) -> None:
        resp = sync_client.communications.get_rfq(ephemeral_rfq)
        assert isinstance(resp, GetRFQResponse)
        assert resp.rfq.id == ephemeral_rfq
        assert_model_fields(resp.rfq)

    def test_delete_rfq(
        self, sync_client: KalshiClient, demo_market_ticker: str,
    ) -> None:
        try:
            resp = sync_client.communications.create_rfq(
                market_ticker=demo_market_ticker,
                rest_remainder=False,
                contracts=1,
            )
        except (KalshiValidationError, KalshiAuthError) as e:
            pytest.skip(f"demo refused create_rfq: {e}")
        assert isinstance(resp, CreateRFQResponse)
        sync_client.communications.delete_rfq(resp.id)

    def test_quote_lifecycle(
        self, sync_client: KalshiClient, ephemeral_rfq: str,
    ) -> None:
        # Full lifecycle: create quote → get → delete. Skips if the demo
        # server refuses self-quoting (RFQ creator responds to their own RFQ).
        try:
            created = sync_client.communications.create_quote(
                rfq_id=ephemeral_rfq,
                yes_bid="0.50",
                no_bid="0.50",
                rest_remainder=False,
            )
        except (KalshiValidationError, KalshiAuthError) as e:
            pytest.skip(f"demo refused create_quote: {e}")
        quote_id = created.id
        try:
            # Demo server may need a beat to propagate.
            import time

            time.sleep(0.5)
            got = sync_client.communications.get_quote(quote_id)
            assert got.quote.id == quote_id
            assert got.quote.rfq_id == ephemeral_rfq
            assert_model_fields(got.quote)
        finally:
            try:
                sync_client.communications.delete_quote(quote_id)
            except Exception:
                logger.warning("cleanup: failed to delete quote %s", quote_id)

    def test_get_unknown_rfq_errors(self, sync_client: KalshiClient) -> None:
        # Demo rejects malformed RFQ IDs with 400 invalid_parameters before the
        # route maps to 404. Assert via the base class to cover either shape —
        # both are failure modes the SDK must surface cleanly.
        with pytest.raises(KalshiError):
            sync_client.communications.get_rfq("rfq-nonexistent-00000000")

    def test_get_unknown_quote_errors(self, sync_client: KalshiClient) -> None:
        with pytest.raises(KalshiError):
            sync_client.communications.get_quote("q-nonexistent-00000000")


@pytest.mark.integration
@pytest.mark.integration_real_api_only
class TestCommunicationsRealApiOnly:
    """Endpoints the demo user lacks permission to exercise.

    Demo-probed findings (v0.11.0 integration run, supersedes 2026-04-18
    audit for this endpoint):
      - GET /communications/quotes: 400 "Either creator_user_id or
        rfq_creator_user_id must be filled" unless one of those filters
        is present. Demo does not permit either unfiltered list or
        rfq_id-only filter. Passes under real-api creds with a
        {quote_creator_user_id | rfq_creator_user_id} filter.
      - Accept/confirm workflow: needs two parties (RFQ creator +
        quote creator) and doesn't work with a single self-quoting
        demo account.
    """

    def test_list_quotes_unfiltered(self, sync_client: KalshiClient) -> None:
        page = sync_client.communications.list_quotes(limit=10)
        assert isinstance(page, Page)

    def test_list_all_quotes(self, sync_client: KalshiClient) -> None:
        for i, quote in enumerate(
            sync_client.communications.list_all_quotes(limit=10),
        ):
            assert isinstance(quote, Quote)
            if i >= 4:
                break

    def test_list_quotes_by_rfq(
        self, sync_client: KalshiClient, demo_market_ticker: str,
    ) -> None:
        # Even with rfq_id, demo requires creator_user_id or
        # rfq_creator_user_id. Under prod-like creds both filters work.
        try:
            rfq = sync_client.communications.create_rfq(
                market_ticker=demo_market_ticker,
                rest_remainder=False,
                contracts=1,
            )
        except (KalshiValidationError, KalshiAuthError) as e:
            pytest.skip(f"demo refused create_rfq: {e}")
        try:
            comms_id = sync_client.communications.get_id().communications_id
            page = sync_client.communications.list_quotes(
                rfq_id=rfq.id, rfq_creator_user_id=comms_id,
            )
            assert isinstance(page, Page)
        finally:
            try:
                sync_client.communications.delete_rfq(rfq.id)
            except Exception:
                logger.warning("cleanup: failed to delete rfq %s", rfq.id)

    def test_accept_and_confirm_quote(
        self, sync_client: KalshiClient, demo_market_ticker: str,
    ) -> None:
        # Requires two parties: one creates RFQ, another quotes, the first
        # accepts, the second confirms. Not possible with a single demo
        # account that self-quotes, so this lives behind the real-API gate.
        rfq = sync_client.communications.create_rfq(
            market_ticker=demo_market_ticker,
            rest_remainder=False,
            contracts=1,
        )
        try:
            quote = sync_client.communications.create_quote(
                rfq_id=rfq.id,
                yes_bid="0.50",
                no_bid="0.50",
                rest_remainder=False,
            )
            sync_client.communications.accept_quote(
                quote.id, accepted_side="yes",
            )
            sync_client.communications.confirm_quote(quote.id)
        finally:
            try:
                sync_client.communications.delete_rfq(rfq.id)
            except Exception:
                logger.warning("cleanup: failed to delete rfq %s", rfq.id)


@pytest.mark.integration
class TestCommunicationsAsync:
    @pytest.mark.asyncio
    async def test_get_id(self, async_client: AsyncKalshiClient) -> None:
        resp = await async_client.communications.get_id()
        assert isinstance(resp, GetCommunicationsIDResponse)
        assert resp.communications_id

    @pytest.mark.asyncio
    async def test_list_rfqs(self, async_client: AsyncKalshiClient) -> None:
        page = await async_client.communications.list_rfqs(limit=10)
        assert isinstance(page, Page)
        for rfq in page.items:
            assert isinstance(rfq, RFQ)

    @pytest.mark.asyncio
    async def test_list_all_rfqs(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        count = 0
        async for rfq in async_client.communications.list_all_rfqs(limit=10):
            assert isinstance(rfq, RFQ)
            count += 1
            if count >= 5:
                break

    @pytest.mark.asyncio
    async def test_create_get_delete_rfq(
        self,
        async_client: AsyncKalshiClient,
        demo_market_ticker: str,
    ) -> None:
        try:
            created = await async_client.communications.create_rfq(
                market_ticker=demo_market_ticker,
                rest_remainder=False,
                contracts=1,
            )
        except (KalshiValidationError, KalshiAuthError) as e:
            pytest.skip(f"demo refused create_rfq: {e}")
        rfq_id = created.id
        try:
            # Demo eventual consistency — mirror the pattern used elsewhere.
            await asyncio.sleep(0.5)
            got = await async_client.communications.get_rfq(rfq_id)
            assert got.rfq.id == rfq_id
        finally:
            await async_client.communications.delete_rfq(rfq_id)

