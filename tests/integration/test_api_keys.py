"""Integration tests for ApiKeysResource — demo lifecycle.

Mints a throwaway RSA keypair in-test, creates a key on demo, verifies
it shows up in list(), then deletes it. Matches v0.11.0 subaccounts
precedent: real lifecycle on demo, cleanup via try/finally so a test
failure mid-flight still removes the key.

Note on leakage: if the delete call itself fails for any reason, the key
survives on the demo account. The finally block catches and logs
exceptions rather than re-raising, so the original assertion failure is
preserved.
"""

from __future__ import annotations

import logging
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.async_client import AsyncKalshiClient
from kalshi.client import KalshiClient
from kalshi.errors import KalshiError
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


def _mint_public_key_pem() -> str:
    """Generate a throwaway RSA-2048 public key in PEM format."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pub_bytes.decode("utf-8")


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
        name = f"sdk-integration-{uuid.uuid4().hex[:8]}"
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
            # Cleanup: swallow delete errors so the original assertion wins.
            try:
                sync_client.api_keys.delete(created.api_key_id)
            except Exception as exc:
                logger.warning(
                    "Cleanup: failed to delete API key %s: %s",
                    created.api_key_id, exc,
                )

    def test_generate_then_delete(self, sync_client: KalshiClient) -> None:
        name = f"sdk-integration-gen-{uuid.uuid4().hex[:8]}"
        try:
            gen = sync_client.api_keys.generate(name=name, scopes=["read"])
        except KalshiError as e:
            pytest.skip(f"demo refused generate API key: {e}")

        assert isinstance(gen, GenerateApiKeyResponse)
        assert gen.api_key_id
        # Private key must be a PEM — exact shape is RSA; loose check avoids
        # brittle dependency on exact header whitespace.
        assert "PRIVATE KEY" in gen.private_key

        try:
            sync_client.api_keys.delete(gen.api_key_id)
        except Exception as exc:
            logger.warning(
                "Cleanup: failed to delete generated key %s: %s",
                gen.api_key_id, exc,
            )


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
        name = f"sdk-integration-async-{uuid.uuid4().hex[:8]}"
        pub_pem = _mint_public_key_pem()
        try:
            created = await async_client.api_keys.create(
                name=name, public_key=pub_pem, scopes=["read"],
            )
        except KalshiError as e:
            pytest.skip(f"demo refused async create API key: {e}")

        assert isinstance(created, CreateApiKeyResponse)

        try:
            await async_client.api_keys.delete(created.api_key_id)
        except Exception as exc:
            logger.warning(
                "Cleanup: failed to async-delete API key %s: %s",
                created.api_key_id, exc,
            )
