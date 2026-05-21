"""API Keys resource — manage programmatic credentials."""

from __future__ import annotations

import builtins
from typing import Any, overload

from kalshi.models.api_keys import (
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    GenerateApiKeyRequest,
    GenerateApiKeyResponse,
    GetApiKeysResponse,
)
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _check_request_exclusive,
    _seg,
)

# Shared request-body builders (issue #46).


def _build_create_api_key_body(
    request: CreateApiKeyRequest | None,
    *,
    name: str | None,
    public_key: str | None,
    scopes: builtins.list[str] | None,
) -> dict[str, Any]:
    _check_request_exclusive(
        request,
        name=name,
        public_key=public_key,
        scopes=scopes,
    )
    if request is None:
        if name is None or public_key is None:
            raise TypeError("create() requires `name` and `public_key` (or pass `request=...`)")
        request = CreateApiKeyRequest(
            name=name,
            public_key=public_key,
            scopes=scopes,
        )
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


def _build_generate_api_key_body(
    request: GenerateApiKeyRequest | None,
    *,
    name: str | None,
    scopes: builtins.list[str] | None,
) -> dict[str, Any]:
    _check_request_exclusive(request, name=name, scopes=scopes)
    if request is None:
        if name is None:
            raise TypeError("generate() requires `name` (or pass `request=...`)")
        request = GenerateApiKeyRequest(name=name, scopes=scopes)
    return request.model_dump(exclude_none=True, by_alias=True, mode="json")


class ApiKeysResource(SyncResource):
    """Sync API keys resource.

    All endpoints require authentication. ``create`` takes a caller-minted
    RSA public key; ``generate`` has Kalshi mint a pair and returns the
    private key once (see :class:`GenerateApiKeyResponse`).
    """

    def list(self, *, extra_headers: dict[str, str] | None = None) -> GetApiKeysResponse:
        self._require_auth()
        data = self._get("/api_keys", extra_headers=extra_headers)
        return GetApiKeysResponse.model_validate(data)

    @overload
    def create(
        self, *, request: CreateApiKeyRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateApiKeyResponse: ...
    @overload
    def create(
        self,
        *,
        name: str,
        public_key: str,
        scopes: builtins.list[str] | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateApiKeyResponse: ...
    def create(
        self,
        *,
        request: CreateApiKeyRequest | None = None,
        name: str | None = None,
        public_key: str | None = None,
        scopes: builtins.list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateApiKeyResponse:
        self._require_auth()
        body = _build_create_api_key_body(
            request,
            name=name,
            public_key=public_key,
            scopes=scopes,
        )
        data = self._post("/api_keys", json=body, extra_headers=extra_headers)
        return CreateApiKeyResponse.model_validate(data)

    @overload
    def generate(
        self, *, request: GenerateApiKeyRequest, extra_headers: dict[str, str] | None = None
    ) -> GenerateApiKeyResponse: ...
    @overload
    def generate(
        self,
        *,
        name: str,
        scopes: builtins.list[str] | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> GenerateApiKeyResponse: ...
    def generate(
        self,
        *,
        request: GenerateApiKeyRequest | None = None,
        name: str | None = None,
        scopes: builtins.list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GenerateApiKeyResponse:
        self._require_auth()
        body = _build_generate_api_key_body(request, name=name, scopes=scopes)
        data = self._post("/api_keys/generate", json=body, extra_headers=extra_headers)
        return GenerateApiKeyResponse.model_validate(data)

    def delete(self, api_key: str, *, extra_headers: dict[str, str] | None = None) -> None:
        self._require_auth()
        self._delete(f"/api_keys/{_seg(api_key, name='api_key')}", extra_headers=extra_headers)


class AsyncApiKeysResource(AsyncResource):
    """Async API keys resource."""

    async def list(self, *, extra_headers: dict[str, str] | None = None) -> GetApiKeysResponse:
        self._require_auth()
        data = await self._get("/api_keys", extra_headers=extra_headers)
        return GetApiKeysResponse.model_validate(data)

    @overload
    async def create(
        self, *, request: CreateApiKeyRequest, extra_headers: dict[str, str] | None = None
    ) -> CreateApiKeyResponse: ...
    @overload
    async def create(
        self,
        *,
        name: str,
        public_key: str,
        scopes: builtins.list[str] | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateApiKeyResponse: ...
    async def create(
        self,
        *,
        request: CreateApiKeyRequest | None = None,
        name: str | None = None,
        public_key: str | None = None,
        scopes: builtins.list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateApiKeyResponse:
        self._require_auth()
        body = _build_create_api_key_body(
            request,
            name=name,
            public_key=public_key,
            scopes=scopes,
        )
        data = await self._post("/api_keys", json=body, extra_headers=extra_headers)
        return CreateApiKeyResponse.model_validate(data)

    @overload
    async def generate(
        self, *, request: GenerateApiKeyRequest, extra_headers: dict[str, str] | None = None
    ) -> GenerateApiKeyResponse: ...
    @overload
    async def generate(
        self,
        *,
        name: str,
        scopes: builtins.list[str] | None = ...,
        extra_headers: dict[str, str] | None = None,
    ) -> GenerateApiKeyResponse: ...
    async def generate(
        self,
        *,
        request: GenerateApiKeyRequest | None = None,
        name: str | None = None,
        scopes: builtins.list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GenerateApiKeyResponse:
        self._require_auth()
        body = _build_generate_api_key_body(request, name=name, scopes=scopes)
        data = await self._post("/api_keys/generate", json=body, extra_headers=extra_headers)
        return GenerateApiKeyResponse.model_validate(data)

    async def delete(self, api_key: str, *, extra_headers: dict[str, str] | None = None) -> None:
        self._require_auth()
        await self._delete(
            f"/api_keys/{_seg(api_key, name='api_key')}", extra_headers=extra_headers
        )
