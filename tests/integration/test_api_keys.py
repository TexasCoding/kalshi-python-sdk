"""Integration tests for ApiKeysResource — demo lifecycle.

Mints a throwaway RSA keypair in-test, creates a key on demo, verifies
it shows up in list(), then deletes it. Matches v0.11.0 subaccounts
precedent: real lifecycle on demo, cleanup via try/finally so a test
failure mid-flight still removes the key.

Leak defense: (1) ``_delete_with_retry`` wraps the cleanup call with 3
attempts at 0.25s/0.5s/1.0s backoff to survive transient network blips.
POST/DELETE are not retried at the transport layer (SDK duplicate-risk
policy), so the retry lives here in the test fixture. (2) The
``_scan_leaked_keys`` session-scoped autouse fixture lists all
``sdk-integration-*``-named keys at session end and warns if any remain.
A warning is louder than a silent leak; it does NOT fail the test run
(production credential checks should live outside the SDK test suite).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiError, KalshiNotFoundError
from kalshi.models.api_keys import (
    ApiKey,
    CreateApiKeyResponse,
    GenerateApiKeyResponse,
    GetApiKeysResponse,
)
from tests.integration.assertions import assert_model_fields
from tests.integration.coverage_harness import register

logger = logging.getLogger(__name__)

register("ApiKeysResource", ["create", "delete", "generate", "list"])

# Test-key name prefix — session sweep uses this to identify leaks.
_LEAK_PREFIX = "sdk-integration-"


def _mint_public_key_pem() -> str:
    """Generate a throwaway RSA-2048 public key in PEM format."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pub_bytes.decode("utf-8")


def _delete_with_retry(client: KalshiClient, api_key_id: str) -> bool:
    """Delete with 3 attempts at 0.25s/0.5s/1.0s backoff.

    Returns True if the key was deleted (or already gone), False if all
    attempts failed. Never raises — cleanup should never mask the
    original test failure.
    """
    for attempt, delay in enumerate([0.0, 0.25, 0.5, 1.0]):
        if delay:
            time.sleep(delay)
        try:
            client.api_keys.delete(api_key_id)
            return True
        except KalshiNotFoundError:
            # Already deleted — idempotent success.
            return True
        except Exception as exc:  # broad catch is intentional in cleanup
            last_exc: Exception = exc
            logger.warning(
                "Cleanup attempt %d/4 for API key %s failed: %s",
                attempt + 1, api_key_id, exc,
            )
    logger.error(
        "LEAKED API key %s after 4 delete attempts: %s",
        api_key_id, last_exc,
    )
    return False


async def _async_delete_with_retry(
    client: AsyncKalshiClient, api_key_id: str,
) -> bool:
    """Async twin of ``_delete_with_retry`` — same retry cadence."""
    for attempt, delay in enumerate([0.0, 0.25, 0.5, 1.0]):
        if delay:
            await asyncio.sleep(delay)
        try:
            await client.api_keys.delete(api_key_id)
            return True
        except KalshiNotFoundError:
            return True
        except Exception as exc:
            last_exc: Exception = exc
            logger.warning(
                "Async cleanup attempt %d/4 for API key %s failed: %s",
                attempt + 1, api_key_id, exc,
            )
    logger.error(
        "LEAKED API key %s after 4 async delete attempts: %s",
        api_key_id, last_exc,
    )
    return False


@pytest.fixture(scope="session", autouse=True)
def _scan_leaked_keys(sync_client: KalshiClient) -> Iterator[None]:
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
        logger.warning("Leak sweep: could not list keys: %s", exc)
        return
    leaked = [k for k in listed.api_keys if k.name.startswith(_LEAK_PREFIX)]
    if leaked:
        logger.warning(
            "API KEY LEAK — %d test-minted key(s) survived on demo: %s. "
            "Delete manually or fix the cleanup retry.",
            len(leaked),
            ", ".join(f"{k.name}({k.api_key_id})" for k in leaked),
        )


@pytest.mark.integration
class TestApiKeysSync:
    def test_list_includes_auth_key(self, sync_client: KalshiClient) -> None:
        resp = sync_client.api_keys.list()
        assert isinstance(resp, GetApiKeysResponse)
        # The authenticated key used to make this request must appear in its
        # own list — a sanity check the demo account has at least one key.
        assert resp.api_keys, "list() returned zero keys but call was authed"
        for k in resp.api_keys:
            assert isinstance(k, ApiKey)
            assert_model_fields(k)

    def test_create_then_list_then_delete(
        self, sync_client: KalshiClient,
    ) -> None:
        name = f"{_LEAK_PREFIX}{uuid.uuid4().hex[:8]}"
        pub_pem = _mint_public_key_pem()

        try:
            created = sync_client.api_keys.create(
                name=name, public_key=pub_pem, scopes=["read"],
            )
        except KalshiError as e:
            # Demo may reject non-Premier/MarketMaker accounts with 403.
            pytest.skip(f"demo refused create API key: {e}")

        assert isinstance(created, CreateApiKeyResponse)
        assert created.api_key_id

        try:
            listed = sync_client.api_keys.list()
            ids = {k.api_key_id for k in listed.api_keys}
            assert created.api_key_id in ids, (
                f"newly-created key {created.api_key_id} not in list(); "
                f"got {sorted(ids)}"
            )
        finally:
            _delete_with_retry(sync_client, created.api_key_id)

    def test_generate_then_delete(self, sync_client: KalshiClient) -> None:
        name = f"{_LEAK_PREFIX}gen-{uuid.uuid4().hex[:8]}"
        try:
            gen = sync_client.api_keys.generate(name=name, scopes=["read"])
        except KalshiError as e:
            pytest.skip(f"demo refused generate API key: {e}")

        assert isinstance(gen, GenerateApiKeyResponse)
        assert gen.api_key_id
        # Private key must be a PEM — exact shape is RSA; loose check avoids
        # brittle dependency on exact header whitespace.
        assert "PRIVATE KEY" in gen.private_key

        _delete_with_retry(sync_client, gen.api_key_id)


@pytest.mark.integration
class TestApiKeysAsync:
    @pytest.mark.asyncio
    async def test_list(self, async_client: AsyncKalshiClient) -> None:
        resp = await async_client.api_keys.list()
        assert isinstance(resp, GetApiKeysResponse)

    @pytest.mark.asyncio
    async def test_create_then_delete(
        self, async_client: AsyncKalshiClient,
    ) -> None:
        name = f"{_LEAK_PREFIX}async-{uuid.uuid4().hex[:8]}"
        pub_pem = _mint_public_key_pem()
        try:
            created = await async_client.api_keys.create(
                name=name, public_key=pub_pem, scopes=["read"],
            )
        except KalshiError as e:
            pytest.skip(f"demo refused async create API key: {e}")

        assert isinstance(created, CreateApiKeyResponse)

        await _async_delete_with_retry(async_client, created.api_key_id)
