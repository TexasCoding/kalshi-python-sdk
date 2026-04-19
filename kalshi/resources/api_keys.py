"""API Keys resource — manage programmatic credentials."""

from __future__ import annotations

import builtins

from kalshi.models.api_keys import (
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    GenerateApiKeyRequest,
    GenerateApiKeyResponse,
    GetApiKeysResponse,
)
from kalshi.resources._base import AsyncResource, SyncResource


class ApiKeysResource(SyncResource):
    """Sync API keys resource.

    All endpoints require authentication. ``create`` takes a caller-minted
    RSA public key; ``generate`` has Kalshi mint a pair and returns the
    private key once (see :class:`GenerateApiKeyResponse`).
    """

    def list(self) -> GetApiKeysResponse:
        self._require_auth()
        data = self._get("/api_keys")
        return GetApiKeysResponse.model_validate(data)

    def create(
        self,
        *,
        name: str,
        public_key: str,
        scopes: builtins.list[str] | None = None,
    ) -> CreateApiKeyResponse:
        self._require_auth()
        req = CreateApiKeyRequest(name=name, public_key=public_key, scopes=scopes)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/api_keys", json=body)
        return CreateApiKeyResponse.model_validate(data)

    def generate(
        self,
        *,
        name: str,
        scopes: builtins.list[str] | None = None,
    ) -> GenerateApiKeyResponse:
        self._require_auth()
        req = GenerateApiKeyRequest(name=name, scopes=scopes)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = self._post("/api_keys/generate", json=body)
        return GenerateApiKeyResponse.model_validate(data)

    def delete(self, api_key: str) -> None:
        self._require_auth()
        self._delete(f"/api_keys/{api_key}")


class AsyncApiKeysResource(AsyncResource):
    """Async API keys resource."""

    async def list(self) -> GetApiKeysResponse:
        self._require_auth()
        data = await self._get("/api_keys")
        return GetApiKeysResponse.model_validate(data)

    async def create(
        self,
        *,
        name: str,
        public_key: str,
        scopes: builtins.list[str] | None = None,
    ) -> CreateApiKeyResponse:
        self._require_auth()
        req = CreateApiKeyRequest(name=name, public_key=public_key, scopes=scopes)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/api_keys", json=body)
        return CreateApiKeyResponse.model_validate(data)

    async def generate(
        self,
        *,
        name: str,
        scopes: builtins.list[str] | None = None,
    ) -> GenerateApiKeyResponse:
        self._require_auth()
        req = GenerateApiKeyRequest(name=name, scopes=scopes)
        body = req.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._post("/api_keys/generate", json=body)
        return GenerateApiKeyResponse.model_validate(data)

    async def delete(self, api_key: str) -> None:
        self._require_auth()
        await self._delete(f"/api_keys/{api_key}")
