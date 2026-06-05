"""Tests for PerpsClient / AsyncPerpsClient construction + lifecycle."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.config import PERPS_DEMO_BASE_URL, PERPS_DEMO_WS_URL


def _encrypted_pem(key: rsa.RSAPrivateKey, password: bytes) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )

_RESOURCE_ATTRS = (
    "exchange",
    "markets",
    "orders",
    "order_groups",
    "portfolio",
    "margin",
    "funding",
    "transfers",
)


class TestSyncConstruction:
    def test_key_path_builds_owned_auth(self, tmp_path, pem_bytes: bytes) -> None:
        key_file = tmp_path / "perps.pem"
        key_file.write_bytes(pem_bytes)
        client = PerpsClient(
            key_id="perps-key",
            private_key_path=str(key_file),
            config=PerpsConfig.demo(),
        )
        assert client.is_authenticated is True
        assert client._auth_owned is True
        client.close()

    def test_caller_owned_auth(self, test_auth: KalshiAuth) -> None:
        client = PerpsClient(auth=test_auth, config=PerpsConfig.demo())
        assert client.is_authenticated is True
        assert client._auth_owned is False
        client.close()

    def test_unauthenticated(self) -> None:
        client = PerpsClient(config=PerpsConfig.demo())
        assert client.is_authenticated is False
        assert client._auth is None
        client.close()

    def test_all_resource_stubs_present(self, test_auth: KalshiAuth) -> None:
        client = PerpsClient(auth=test_auth, config=PerpsConfig.demo())
        for attr in _RESOURCE_ATTRS:
            assert getattr(client, attr) is not None, attr
        client.close()

    def test_both_key_sources_raises(self, pem_bytes: bytes) -> None:
        with pytest.raises(ValueError, match="not both"):
            PerpsClient(
                key_id="k",
                private_key_path="/tmp/x.pem",
                private_key=pem_bytes,
                config=PerpsConfig.demo(),
            )

    def test_empty_key_id_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            PerpsClient(key_id="   ", config=PerpsConfig.demo())

    def test_demo_with_conflicting_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Conflicting environment"):
            PerpsClient(demo=True, base_url="https://external-api.kalshi.com/trade-api/v2")

    def test_demo_flag_resolves_demo_urls(self) -> None:
        client = PerpsClient(demo=True)
        assert client._config.base_url == PERPS_DEMO_BASE_URL
        client.close()

    def test_context_manager(self, test_auth: KalshiAuth) -> None:
        with PerpsClient(auth=test_auth, config=PerpsConfig.demo()) as client:
            assert client.is_authenticated is True


class TestFromEnv:
    def test_from_env_reads_perps_vars(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_PERPS_KEY_ID", "perps-env-key")
        monkeypatch.setenv("KALSHI_PERPS_PRIVATE_KEY", pem_string)
        monkeypatch.setenv("KALSHI_PERPS_DEMO", "true")
        client = PerpsClient.from_env()
        assert client.is_authenticated is True
        # from_env built the auth → client owns it.
        assert client._auth_owned is True
        assert client._config.base_url == PERPS_DEMO_BASE_URL
        client.close()

    def test_from_env_does_not_read_prediction_vars(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        # Prediction-API creds must NOT authenticate a perps client.
        monkeypatch.setenv("KALSHI_KEY_ID", "prediction-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_PERPS_KEY_ID", raising=False)
        client = PerpsClient.from_env()
        assert client.is_authenticated is False
        client.close()

    def test_from_env_unauthenticated_when_no_creds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_PERPS_KEY_ID", raising=False)
        client = PerpsClient.from_env()
        assert client.is_authenticated is False
        client.close()

    def test_from_env_caller_auth_not_overwritten(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str, test_auth: KalshiAuth
    ) -> None:
        monkeypatch.setenv("KALSHI_PERPS_KEY_ID", "perps-env-key")
        monkeypatch.setenv("KALSHI_PERPS_PRIVATE_KEY", pem_string)
        client = PerpsClient.from_env(auth=test_auth, config=PerpsConfig.demo())
        assert client._auth is test_auth
        assert client._auth_owned is False  # caller-supplied auth stays caller-owned
        client.close()


class TestAsyncConstruction:
    async def test_async_resource_stubs_present(self, test_auth: KalshiAuth) -> None:
        client = AsyncPerpsClient(auth=test_auth, config=PerpsConfig.demo())
        for attr in _RESOURCE_ATTRS:
            assert getattr(client, attr) is not None, attr
        await client.close()

    async def test_async_context_manager(self, test_auth: KalshiAuth) -> None:
        async with AsyncPerpsClient(auth=test_auth, config=PerpsConfig.demo()) as client:
            assert client.is_authenticated is True

    async def test_async_from_env(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_PERPS_KEY_ID", "perps-env-key")
        monkeypatch.setenv("KALSHI_PERPS_PRIVATE_KEY", pem_string)
        client = AsyncPerpsClient.from_env(demo=True)
        assert client.is_authenticated is True
        assert client._auth_owned is True
        await client.close()


class TestIssue406ConfigShorthandGuards:
    """#406: reject config= combined with env-determining shorthand; ws_base_url
    shorthand reaches the config."""

    def test_config_plus_demo_raises(self) -> None:
        # The real-money footgun: demo=True silently ignored when config given.
        with pytest.raises(ValueError, match="not both"):
            PerpsClient(config=PerpsConfig.production(), demo=True)

    def test_config_plus_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            PerpsClient(config=PerpsConfig.demo(), base_url=PERPS_DEMO_BASE_URL)

    def test_config_plus_ws_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            PerpsClient(config=PerpsConfig.demo(), ws_base_url=PERPS_DEMO_WS_URL)

    def test_ws_base_url_shorthand_threads_to_config(self) -> None:
        client = PerpsClient(base_url=PERPS_DEMO_BASE_URL, ws_base_url=PERPS_DEMO_WS_URL)
        assert client._config.base_url == PERPS_DEMO_BASE_URL
        assert client._config.ws_base_url == PERPS_DEMO_WS_URL
        client.close()


class TestIssue410EncryptedKeyPassword:
    """#410: a `password=` for an encrypted private key is threaded to the signer."""

    def test_password_threaded_for_encrypted_pem(
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        # Without threading the password, load of the encrypted PEM would raise
        # at construction — so a successful authenticated client proves the fix.
        enc = _encrypted_pem(rsa_private_key, b"sekret")
        client = PerpsClient(
            key_id="k", private_key=enc, password="sekret", config=PerpsConfig.demo()
        )
        assert client.is_authenticated is True
        client.close()

    async def test_password_threaded_async(
        self, rsa_private_key: rsa.RSAPrivateKey
    ) -> None:
        enc = _encrypted_pem(rsa_private_key, b"sekret")
        client = AsyncPerpsClient(
            key_id="k", private_key=enc, password="sekret", config=PerpsConfig.demo()
        )
        assert client.is_authenticated is True
        await client.close()
