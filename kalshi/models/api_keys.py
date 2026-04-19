"""API Key models — programmatic credentials management.

API keys allow programmatic access without username/password. Each key
has a unique ``api_key_id`` and a user-provided ``name`` for bookkeeping.
``create`` accepts a caller-supplied RSA public key (PEM); ``generate``
has Kalshi mint a fresh key pair and returns the private key once
(store it — it cannot be retrieved again).
"""

from __future__ import annotations

from pydantic import BaseModel

from kalshi.types import NullableList


class ApiKey(BaseModel):
    """An API key registered on the authenticated user's account."""

    api_key_id: str
    name: str
    scopes: list[str]

    model_config = {"extra": "allow"}


class GetApiKeysResponse(BaseModel):
    """Response from GET /api_keys.

    ``api_keys`` uses NullableList since Kalshi has returned JSON null
    for required list fields in other envelopes (see v0.9.0 Series fix).
    Coercing None -> [] matches the envelope-list pattern established
    across the rest of the SDK.
    """

    api_keys: NullableList[ApiKey] = []

    model_config = {"extra": "allow"}


class CreateApiKeyRequest(BaseModel):
    """Body for POST /api_keys — register a caller-supplied public key.

    ``public_key`` must be a PEM-encoded RSA public key (i.e. starts
    with ``-----BEGIN PUBLIC KEY-----``). ``scopes`` defaults to full
    access (``["read", "write"]``) server-side when omitted. If
    ``"write"`` is included, ``"read"`` must be too.
    """

    name: str
    public_key: str
    scopes: list[str] | None = None

    model_config = {"extra": "forbid"}


class CreateApiKeyResponse(BaseModel):
    """Response from POST /api_keys — the new key's ID."""

    api_key_id: str

    model_config = {"extra": "allow"}


class GenerateApiKeyRequest(BaseModel):
    """Body for POST /api_keys/generate — let Kalshi mint a key pair."""

    name: str
    scopes: list[str] | None = None

    model_config = {"extra": "forbid"}


class GenerateApiKeyResponse(BaseModel):
    """Response from POST /api_keys/generate.

    ``private_key`` is a PEM-encoded RSA private key returned ONLY in this
    response. Store it securely — Kalshi does not retain a copy and it
    cannot be retrieved later.
    """

    api_key_id: str
    private_key: str

    model_config = {"extra": "allow"}
