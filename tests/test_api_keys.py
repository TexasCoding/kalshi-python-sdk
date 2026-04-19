"""Tests for kalshi.resources.api_keys — API key lifecycle."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import (
    AuthRequiredError,
    KalshiAuthError,
    KalshiNotFoundError,
    KalshiValidationError,
)
from kalshi.models.api_keys import (
    ApiKey,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    GenerateApiKeyRequest,
    GenerateApiKeyResponse,
    GetApiKeysResponse,
)
from kalshi.resources.api_keys import ApiKeysResource, AsyncApiKeysResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def api_keys(test_auth: KalshiAuth, config: KalshiConfig) -> ApiKeysResource:
    return ApiKeysResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_api_keys(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncApiKeysResource:
    return AsyncApiKeysResource(AsyncTransport(test_auth, config))


@pytest.fixture
def unauth_api_keys(config: KalshiConfig) -> ApiKeysResource:
    return ApiKeysResource(SyncTransport(None, config))


# Test RSA public key for use in create() calls (not a real key; just PEM-shaped).
_PUBKEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...truncated...\n"
    "-----END PUBLIC KEY-----"
)


class TestApiKeyModels:
    def test_api_key_parses(self) -> None:
        k = ApiKey.model_validate(
            {"api_key_id": "k-1", "name": "bot", "scopes": ["read", "write"]},
        )
        assert k.api_key_id == "k-1"
        assert k.name == "bot"
        assert k.scopes == ["read", "write"]

    def test_get_api_keys_response_wraps_list(self) -> None:
        resp = GetApiKeysResponse.model_validate(
            {
                "api_keys": [
                    {"api_key_id": "k-1", "name": "bot", "scopes": ["read"]},
                    {"api_key_id": "k-2", "name": "web", "scopes": ["read", "write"]},
                ],
            },
        )
        assert len(resp.api_keys) == 2

    def test_generate_response_carries_private_key(self) -> None:
        resp = GenerateApiKeyResponse.model_validate(
            {"api_key_id": "k-9", "private_key": "-----BEGIN..."},
        )
        assert resp.api_key_id == "k-9"
        # SecretStr: masked in repr/logs, retrieve via get_secret_value().
        assert resp.private_key.get_secret_value().startswith("-----BEGIN")
        assert "-----BEGIN" not in repr(resp)

    def test_create_request_serializes(self) -> None:
        req = CreateApiKeyRequest(
            name="bot", public_key=_PUBKEY_PEM, scopes=["read"],
        )
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {
            "name": "bot", "public_key": _PUBKEY_PEM, "scopes": ["read"],
        }

    def test_create_request_omits_none_scopes(self) -> None:
        req = CreateApiKeyRequest(name="bot", public_key=_PUBKEY_PEM)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"name": "bot", "public_key": _PUBKEY_PEM}

    def test_create_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            CreateApiKeyRequest(  # type: ignore[call-arg]
                name="bot", public_key=_PUBKEY_PEM, phantom=True,
            )

    def test_generate_request_serializes(self) -> None:
        req = GenerateApiKeyRequest(name="bot")
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert body == {"name": "bot"}

    def test_generate_request_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            GenerateApiKeyRequest(  # type: ignore[call-arg]
                name="bot", phantom="x",
            )


class TestApiKeysList:
    @respx.mock
    def test_list_returns_keys(self, api_keys: ApiKeysResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(
                200,
                json={"api_keys": [
                    {"api_key_id": "k-1", "name": "bot", "scopes": ["read"]},
                ]},
            ),
        )
        resp = api_keys.list()
        assert isinstance(resp, GetApiKeysResponse)
        assert len(resp.api_keys) == 1

    @respx.mock
    def test_list_empty(self, api_keys: ApiKeysResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(200, json={"api_keys": []}),
        )
        assert api_keys.list().api_keys == []

    @respx.mock
    def test_list_handles_null_api_keys(self, api_keys: ApiKeysResource) -> None:
        """NullableList[ApiKey]: server-sent ``null`` must coerce to ``[]``."""
        respx.get("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(200, json={"api_keys": None}),
        )
        assert api_keys.list().api_keys == []

    @respx.mock
    def test_list_handles_null_scopes(self, api_keys: ApiKeysResource) -> None:
        """NullableList[str] on ApiKey.scopes: server-sent ``null`` coerces to ``[]``."""
        respx.get("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(
                200,
                json={
                    "api_keys": [
                        {"api_key_id": "k-1", "name": "nm", "scopes": None},
                    ],
                },
            ),
        )
        resp = api_keys.list()
        assert resp.api_keys[0].scopes == []

    def test_list_requires_auth(self, unauth_api_keys: ApiKeysResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_api_keys.list()

    @respx.mock
    def test_list_401_raises(self, api_keys: ApiKeysResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(401, json={"message": "nope"}),
        )
        with pytest.raises(KalshiAuthError):
            api_keys.list()


class TestApiKeysCreate:
    @respx.mock
    def test_create_sends_body(self, api_keys: ApiKeysResource) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(201, json={"api_key_id": "k-new"}),
        )
        resp = api_keys.create(name="bot", public_key=_PUBKEY_PEM)
        assert isinstance(resp, CreateApiKeyResponse)
        assert resp.api_key_id == "k-new"
        body = json.loads(route.calls[0].request.content)
        assert body == {"name": "bot", "public_key": _PUBKEY_PEM}

    @respx.mock
    def test_create_with_scopes(self, api_keys: ApiKeysResource) -> None:
        route = respx.post("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(201, json={"api_key_id": "k-new"}),
        )
        api_keys.create(
            name="bot", public_key=_PUBKEY_PEM, scopes=["read", "write"],
        )
        body = json.loads(route.calls[0].request.content)
        assert body["scopes"] == ["read", "write"]

    @respx.mock
    def test_create_400_maps(self, api_keys: ApiKeysResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(400, json={"message": "bad key"}),
        )
        with pytest.raises(KalshiValidationError):
            api_keys.create(name="bot", public_key="not-pem")

    def test_create_requires_auth(self, unauth_api_keys: ApiKeysResource) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_api_keys.create(name="bot", public_key=_PUBKEY_PEM)


class TestApiKeysGenerate:
    @respx.mock
    def test_generate_returns_private_key(
        self, api_keys: ApiKeysResource,
    ) -> None:
        route = respx.post(
            "https://test.kalshi.com/trade-api/v2/api_keys/generate",
        ).mock(
            return_value=httpx.Response(
                201,
                json={"api_key_id": "k-auto", "private_key": "-----BEGIN..."},
            ),
        )
        resp = api_keys.generate(name="bot")
        assert isinstance(resp, GenerateApiKeyResponse)
        assert resp.api_key_id == "k-auto"
        assert resp.private_key.get_secret_value().startswith("-----BEGIN")
        body = json.loads(route.calls[0].request.content)
        assert body == {"name": "bot"}

    def test_generate_requires_auth(
        self, unauth_api_keys: ApiKeysResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_api_keys.generate(name="bot")


class TestApiKeysDelete:
    @respx.mock
    def test_delete_returns_none_on_204(
        self, api_keys: ApiKeysResource,
    ) -> None:
        route = respx.delete(
            "https://test.kalshi.com/trade-api/v2/api_keys/k-1",
        ).mock(return_value=httpx.Response(204))
        assert api_keys.delete("k-1") is None
        assert route.called

    @respx.mock
    def test_delete_404_maps(self, api_keys: ApiKeysResource) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/api_keys/missing",
        ).mock(return_value=httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(KalshiNotFoundError):
            api_keys.delete("missing")

    def test_delete_requires_auth(
        self, unauth_api_keys: ApiKeysResource,
    ) -> None:
        with pytest.raises(AuthRequiredError):
            unauth_api_keys.delete("k-1")


class TestAsyncApiKeys:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list(self, async_api_keys: AsyncApiKeysResource) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(
                200,
                json={"api_keys": [
                    {"api_key_id": "k-1", "name": "bot", "scopes": ["read"]},
                ]},
            ),
        )
        resp = await async_api_keys.list()
        assert len(resp.api_keys) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_create(self, async_api_keys: AsyncApiKeysResource) -> None:
        respx.post("https://test.kalshi.com/trade-api/v2/api_keys").mock(
            return_value=httpx.Response(201, json={"api_key_id": "k-new"}),
        )
        resp = await async_api_keys.create(name="bot", public_key=_PUBKEY_PEM)
        assert resp.api_key_id == "k-new"

    @respx.mock
    @pytest.mark.asyncio
    async def test_generate(
        self, async_api_keys: AsyncApiKeysResource,
    ) -> None:
        respx.post(
            "https://test.kalshi.com/trade-api/v2/api_keys/generate",
        ).mock(
            return_value=httpx.Response(
                201,
                json={"api_key_id": "k-auto", "private_key": "-----BEGIN..."},
            ),
        )
        resp = await async_api_keys.generate(name="bot")
        assert resp.private_key.get_secret_value().startswith("-----BEGIN")

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete(
        self, async_api_keys: AsyncApiKeysResource,
    ) -> None:
        respx.delete(
            "https://test.kalshi.com/trade-api/v2/api_keys/k-1",
        ).mock(return_value=httpx.Response(204))
        assert await async_api_keys.delete("k-1") is None
