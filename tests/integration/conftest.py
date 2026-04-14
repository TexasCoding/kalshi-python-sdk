"""Integration test fixtures — credentials, clients, helpers.

Requires environment variables:
    KALSHI_KEY_ID           — Kalshi API key identifier
    KALSHI_PRIVATE_KEY_PATH — Path to .pem private key file
    KALSHI_DEMO=true        — Route to demo environment

Tests auto-skip when credentials are absent.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.markets import Market

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

DEMO_HOST = "demo-api.kalshi.co"


def _bridge_env_vars() -> None:
    """Map KALSHI_DEMO_* env vars to KALSHI_* for from_env() compatibility.

    Supports both naming conventions:
      .env style:  KALSHI_DEMO_KEY_ID, KALSHI_DEMO_PRIVATE_KEY_PATH
      from_env():  KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH, KALSHI_DEMO=true
    """
    if os.environ.get("KALSHI_DEMO_KEY_ID") and not os.environ.get("KALSHI_KEY_ID"):
        os.environ["KALSHI_KEY_ID"] = os.environ["KALSHI_DEMO_KEY_ID"]
    if os.environ.get("KALSHI_DEMO_PRIVATE_KEY_PATH") and not os.environ.get(
        "KALSHI_PRIVATE_KEY_PATH"
    ):
        os.environ["KALSHI_PRIVATE_KEY_PATH"] = os.environ["KALSHI_DEMO_PRIVATE_KEY_PATH"]
    os.environ.setdefault("KALSHI_DEMO", "true")


_bridge_env_vars()


def _credentials_available() -> bool:
    return bool(os.environ.get("KALSHI_KEY_ID"))


def _assert_demo_url(base_url: str) -> None:
    """Hard-fail if the client is not pointed at the demo environment."""
    if DEMO_HOST not in base_url:
        pytest.fail(
            f"SAFETY: Integration tests must run against the demo API. "
            f"Resolved base_url is '{base_url}', expected '{DEMO_HOST}'. "
            f"Check KALSHI_API_BASE_URL and KALSHI_DEMO env vars."
        )


# ---------------------------------------------------------------------------
# Session-scoped test run ID for order isolation
# ---------------------------------------------------------------------------
TEST_RUN_ID = f"test-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def sync_client() -> Iterator[KalshiClient]:
    if not _credentials_available():
        pytest.skip("KALSHI_KEY_ID not set — skipping integration tests")
    os.environ.setdefault("KALSHI_DEMO", "true")
    client = KalshiClient.from_env()
    _assert_demo_url(client._config.base_url)
    yield client
    client.close()


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncKalshiClient]:
    if not _credentials_available():
        pytest.skip("KALSHI_KEY_ID not set — skipping integration tests")
    os.environ.setdefault("KALSHI_DEMO", "true")
    client = AsyncKalshiClient.from_env()
    _assert_demo_url(client._config.base_url)
    yield client
    try:
        await client.close()
    except RuntimeError:
        pass  # Event loop closing during teardown — safe to ignore


# ---------------------------------------------------------------------------
# Test run ID for order tagging
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def test_run_id() -> str:
    return TEST_RUN_ID


# ---------------------------------------------------------------------------
# Market discovery — find a tradable market on the demo server
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def demo_market(sync_client: KalshiClient) -> Market:
    """Find an active market on the demo server."""
    page = sync_client.markets.list(status="open", limit=10)
    if not page.items:
        pytest.skip("No active markets on demo server")
    return page.items[0]


@pytest.fixture(scope="session")
def demo_market_ticker(demo_market: Market) -> str:
    return demo_market.ticker


@pytest.fixture(scope="session")
def demo_event_ticker(demo_market: Market) -> str:
    ticker = demo_market.event_ticker
    if not ticker:
        pytest.skip("Demo market has no event_ticker")
    return ticker


# ---------------------------------------------------------------------------
# Non-marketable price for order tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def non_marketable_price(sync_client: KalshiClient, demo_market_ticker: str) -> str:
    """Return a price far from the market that will rest on the book.

    Uses $0.01 (1 cent) for yes side — virtually guaranteed to not fill
    unless the market is extremely close to $0.00.
    Returns a string for compatibility with both create() (accepts str)
    and CreateOrderRequest (wraps via to_decimal).
    """
    return "0.01"


# ---------------------------------------------------------------------------
# Balance pre-flight check for order tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def demo_balance_cents(sync_client: KalshiClient) -> int:
    """Return the demo account balance in cents. Skip order tests if too low."""
    balance = sync_client.portfolio.balance()
    return balance.balance


def skip_if_low_balance(balance_cents: int, threshold_cents: int = 1000) -> None:
    """Skip test if balance is below threshold (default $10)."""
    if balance_cents < threshold_cents:
        pytest.skip(
            f"Demo balance too low ({balance_cents} cents < {threshold_cents}). "
            f"Skipping order tests."
        )


# ---------------------------------------------------------------------------
# Session-end cleanup sweep for orphan orders
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def cleanup_orders(sync_client: KalshiClient) -> Iterator[None]:
    """After all tests, cancel any resting orders from this test run."""
    yield
    try:
        page = sync_client.orders.list(status="resting")
        for order in page.items:
            if order.client_order_id and order.client_order_id.startswith(TEST_RUN_ID):
                try:
                    sync_client.orders.cancel(order.order_id)
                    logger.info("Cleanup: cancelled order %s", order.order_id)
                except Exception:
                    logger.warning("Cleanup: failed to cancel order %s", order.order_id)
    except Exception:
        logger.warning("Cleanup: failed to list orders for cleanup sweep")
