"""Integration test fixtures — credentials, clients, helpers.

Requires environment variables:
    KALSHI_KEY_ID           — Kalshi API key identifier
    KALSHI_PRIVATE_KEY_PATH — Path to .pem private key file
    KALSHI_DEMO=true        — Route to demo environment

Tests auto-skip when credentials are absent.

Tests marked ``@pytest.mark.integration_real_api_only`` auto-skip under
the default run — they exercise endpoints the demo server cannot service
(auth-gated roles, demo-broken routes). Enable explicitly by setting
``KALSHI_ENABLE_REAL_API_ONLY=1`` against a prod-like account, or by
running ``pytest -m integration_real_api_only`` with that env var set.
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.models.markets import Market
from kalshi.perps.async_client import AsyncPerpsClient
from kalshi.perps.client import PerpsClient
from kalshi.perps.ws.client import PerpsWebSocket
from kalshi.ws.client import KalshiWebSocket


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item],
) -> None:
    """Skip ``integration_real_api_only`` tests unless explicitly enabled."""
    if os.environ.get("KALSHI_ENABLE_REAL_API_ONLY") == "1":
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "integration_real_api_only: demo cannot service this endpoint "
            "(auth-gated or demo-broken). Set KALSHI_ENABLE_REAL_API_ONLY=1 "
            "to run against a prod-like account."
        ),
    )
    for item in items:
        if "integration_real_api_only" in item.keywords:
            item.add_marker(skip_marker)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

DEMO_HOST = "demo-api.kalshi.co"


@pytest.fixture(scope="session")
def _monkeypatch_session() -> Iterator[pytest.MonkeyPatch]:
    """Session-scoped ``pytest.MonkeyPatch`` (pytest ships only a
    function-scoped fixture). All mutations restore at session end."""
    with pytest.MonkeyPatch.context() as mp:
        yield mp


@pytest.fixture(scope="session", autouse=True)
def _bridge_env_vars(
    _monkeypatch_session: pytest.MonkeyPatch,
) -> None:
    """Map KALSHI_DEMO_* env vars to KALSHI_* for from_env() compatibility.

    Supports both naming conventions:
      .env style:  KALSHI_DEMO_KEY_ID, KALSHI_DEMO_PRIVATE_KEY_PATH
      from_env():  KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH, KALSHI_DEMO=true

    Bridged through ``_monkeypatch_session`` so the mutations are
    automatically rolled back when the integration session ends.
    Previously the same logic ran at conftest import time, leaking
    demo credentials into any unit test that read ``os.environ``
    without an explicit override (e.g. running ``pytest tests/`` would
    silently bridge demo creds for the whole process).
    """
    demo_key_id = os.environ.get("KALSHI_DEMO_KEY_ID")
    if demo_key_id and not os.environ.get("KALSHI_KEY_ID"):
        _monkeypatch_session.setenv("KALSHI_KEY_ID", demo_key_id)
    demo_path = os.environ.get("KALSHI_DEMO_PRIVATE_KEY_PATH")
    if demo_path and not os.environ.get("KALSHI_PRIVATE_KEY_PATH"):
        _monkeypatch_session.setenv("KALSHI_PRIVATE_KEY_PATH", demo_path)
    if "KALSHI_DEMO" not in os.environ:
        _monkeypatch_session.setenv("KALSHI_DEMO", "true")


def _credentials_available() -> bool:
    return bool(os.environ.get("KALSHI_KEY_ID"))


def _assert_demo_url(base_url: str, ws_base_url: str | None = None) -> None:
    """Hard-fail if the client is not pointed at the demo environment."""
    if DEMO_HOST not in base_url:
        pytest.fail(
            f"SAFETY: Integration tests must run against the demo API. "
            f"Resolved base_url is '{base_url}', expected '{DEMO_HOST}'. "
            f"Check KALSHI_API_BASE_URL and KALSHI_DEMO env vars."
        )
    if ws_base_url is not None and DEMO_HOST not in ws_base_url:
        pytest.fail(
            f"SAFETY: WS integration tests must run against the demo API. "
            f"Resolved ws_base_url is '{ws_base_url}', expected '{DEMO_HOST}'. "
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
    _assert_demo_url(client._config.base_url, client._config.ws_base_url)
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
    _assert_demo_url(client._config.base_url, client._config.ws_base_url)
    yield client
    with contextlib.suppress(RuntimeError):
        await client.close()  # Event loop may be closing during teardown


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


# ---------------------------------------------------------------------------
# Session-end leak sweep for API keys minted by integration tests
# ---------------------------------------------------------------------------
# Test-key name prefix — session sweep uses this to identify leaks.
# Lives in conftest (not test_api_keys.py) so the autouse sweep runs on EVERY
# integration session, even when test_api_keys.py isn't collected.
API_KEY_LEAK_PREFIX = "sdk-integration-"


@pytest.fixture(scope="session", autouse=True)
def scan_leaked_api_keys(sync_client: KalshiClient) -> Iterator[None]:
    """Session-end sweep: warn about any surviving ``sdk-integration-*`` keys.

    Does NOT auto-delete — a leak should be loud, not silent. If this
    fires, inspect the demo account and either drain manually or tighten
    the retry logic. Warns (does not fail) so a single cleanup failure
    doesn't red the whole integration suite.
    """
    yield
    try:
        listed = sync_client.api_keys.list()
    except Exception as exc:
        logger.warning("API key leak sweep: could not list keys: %s", exc)
        return
    leaked = [k for k in listed.api_keys if k.name.startswith(API_KEY_LEAK_PREFIX)]
    if leaked:
        logger.warning(
            "API KEY LEAK — %d test-minted key(s) survived on demo: %s. "
            "Delete manually or fix the cleanup retry.",
            len(leaked),
            ", ".join(f"{k.name}({k.api_key_id})" for k in leaked),
        )


# ---------------------------------------------------------------------------
# WebSocket connection fixture
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def ws_session(sync_client: KalshiClient) -> AsyncIterator[KalshiWebSocket]:
    """Connect to demo WS, yield an active session, clean up on exit."""
    config = sync_client._config
    _assert_demo_url(config.base_url, config.ws_base_url)

    auth = sync_client._auth
    ws = KalshiWebSocket(auth=auth, config=config)
    async with ws.connect() as session:
        yield session


# ===========================================================================
# Perps (margin) integration fixtures
# ===========================================================================
# The perps API lives on its own host with a separate credential namespace
# (``KALSHI_PERPS_*``). These fixtures mirror the prediction-API fixtures above:
# auto-skip when perps credentials are absent, and hard-fail unless the resolved
# base/WS URL is the demo host.

PERPS_DEMO_REST_HOST = "external-api.demo.kalshi.co"
PERPS_DEMO_WS_HOST = "external-api-margin-ws.demo.kalshi.co"

# Session-scoped run ID for perps order isolation (mirrors TEST_RUN_ID).
PERPS_TEST_RUN_ID = f"perps-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session", autouse=True)
def _bridge_perps_env_vars(
    _monkeypatch_session: pytest.MonkeyPatch,
) -> None:
    """Map ``KALSHI_DEMO_*`` env vars to ``KALSHI_PERPS_*`` for from_env().

    Perps ``from_env()`` reads a separate ``KALSHI_PERPS_*`` namespace. To let a
    single demo credential set drive both suites, bridge the ``.env`` style
    ``KALSHI_DEMO_*`` vars into the perps namespace when the perps vars are not
    already set. Bridged through ``_monkeypatch_session`` so mutations roll back
    at session end (no leak into unit tests reading ``os.environ``).
    """
    demo_key_id = os.environ.get("KALSHI_DEMO_KEY_ID")
    if demo_key_id and not os.environ.get("KALSHI_PERPS_KEY_ID"):
        _monkeypatch_session.setenv("KALSHI_PERPS_KEY_ID", demo_key_id)
    demo_path = os.environ.get("KALSHI_DEMO_PRIVATE_KEY_PATH")
    if demo_path and not os.environ.get("KALSHI_PERPS_PRIVATE_KEY_PATH"):
        _monkeypatch_session.setenv("KALSHI_PERPS_PRIVATE_KEY_PATH", demo_path)
    if "KALSHI_PERPS_DEMO" not in os.environ:
        _monkeypatch_session.setenv("KALSHI_PERPS_DEMO", "true")


def _perps_credentials_available() -> bool:
    return bool(os.environ.get("KALSHI_PERPS_KEY_ID"))


def _assert_perps_demo_url(base_url: str, ws_base_url: str | None = None) -> None:
    """Hard-fail if the perps client is not pointed at the demo environment."""
    if PERPS_DEMO_REST_HOST not in base_url:
        pytest.fail(
            f"SAFETY: Perps integration tests must run against the demo API. "
            f"Resolved base_url is '{base_url}', expected '{PERPS_DEMO_REST_HOST}'. "
            f"Check KALSHI_PERPS_API_BASE_URL and KALSHI_PERPS_DEMO env vars."
        )
    if ws_base_url is not None and PERPS_DEMO_WS_HOST not in ws_base_url:
        pytest.fail(
            f"SAFETY: Perps WS integration tests must run against the demo API. "
            f"Resolved ws_base_url is '{ws_base_url}', expected "
            f"'{PERPS_DEMO_WS_HOST}'. "
            f"Check KALSHI_PERPS_API_BASE_URL and KALSHI_PERPS_DEMO env vars."
        )


@pytest.fixture(scope="session")
def perps_test_run_id() -> str:
    return PERPS_TEST_RUN_ID


@pytest.fixture(scope="session")
def perps_sync_client() -> Iterator[PerpsClient]:
    if not _perps_credentials_available():
        pytest.skip("KALSHI_PERPS_KEY_ID not set — skipping perps integration tests")
    os.environ.setdefault("KALSHI_PERPS_DEMO", "true")
    client = PerpsClient.from_env()
    _assert_perps_demo_url(client._config.base_url, client._config.ws_base_url)
    yield client
    client.close()


@pytest_asyncio.fixture
async def perps_async_client() -> AsyncIterator[AsyncPerpsClient]:
    if not _perps_credentials_available():
        pytest.skip("KALSHI_PERPS_KEY_ID not set — skipping perps integration tests")
    os.environ.setdefault("KALSHI_PERPS_DEMO", "true")
    client = AsyncPerpsClient.from_env()
    _assert_perps_demo_url(client._config.base_url, client._config.ws_base_url)
    yield client
    with contextlib.suppress(RuntimeError):
        await client.close()  # Event loop may be closing during teardown


def skip_if_not_margin_enabled(client: PerpsClient) -> None:
    """Skip if the demo account is not margin-enabled (``GetMarginEnabled`` False)."""
    if not client.is_authenticated:
        pytest.skip("Perps client unauthenticated — cannot check margin access")
    if not client.exchange.enabled().enabled:
        pytest.skip("Demo account is not margin-enabled — skipping perps test")


def skip_if_no_margin_markets(client: PerpsClient) -> list[str]:
    """Return tradable margin market tickers; skip if the demo has none."""
    markets = client.markets.list()
    if not markets:
        pytest.skip("No margin markets on demo server — skipping perps test")
    return [m.ticker for m in markets]


@pytest.fixture(scope="session")
def perps_market_ticker(perps_sync_client: PerpsClient) -> str:
    """Find a margin market on the demo server; skip if none exist."""
    tickers = skip_if_no_margin_markets(perps_sync_client)
    return tickers[0]


@pytest.fixture(scope="session", autouse=True)
def cleanup_perps_orders(perps_sync_client: PerpsClient) -> Iterator[None]:
    """After all tests, cancel any resting margin orders from this test run.

    Mirrors :func:`cleanup_orders` — matches on the ``PERPS_TEST_RUN_ID``-tagged
    ``client_order_id`` so live perps order tests never leak.
    """
    yield
    if not perps_sync_client.is_authenticated:
        return
    try:
        resp = perps_sync_client.orders.list(status="resting")
    except Exception:
        logger.warning("Perps cleanup: failed to list orders for cleanup sweep")
        return
    for order in resp.orders:
        if order.client_order_id and order.client_order_id.startswith(PERPS_TEST_RUN_ID):
            try:
                perps_sync_client.orders.cancel(order.order_id)
                logger.info("Perps cleanup: cancelled order %s", order.order_id)
            except Exception:
                logger.warning(
                    "Perps cleanup: failed to cancel order %s", order.order_id
                )


@pytest_asyncio.fixture
async def perps_ws_session(
    perps_sync_client: PerpsClient,
) -> AsyncIterator[PerpsWebSocket]:
    """Connect to the demo margin WS, yield an active session, clean up on exit.

    Mirrors :func:`ws_session`. The perps WS requires a (non-None) auth signer,
    so this skips an unauthenticated perps client.
    """
    config = perps_sync_client._config
    _assert_perps_demo_url(config.base_url, config.ws_base_url)

    auth = perps_sync_client._auth
    if auth is None:
        pytest.skip("Perps client unauthenticated — cannot open margin WS")
    ws = PerpsWebSocket(auth=auth, config=config)
    async with ws.connect() as session:
        yield session
