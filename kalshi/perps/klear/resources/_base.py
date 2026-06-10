"""Klear (SCM) resource bases that inject the Bearer ``Authorization`` header.

Klear authenticates with a static ``Authorization: Bearer <admin_user_id>:<access_token>``
header (not RSA-PSS), so the transport is built with ``auth=None``. These bases
reuse the prediction-API transport/HTTP helpers but override ``_get``/``_post``
to merge the Klear Bearer header onto every request — the paginators
(``_list``/``_list_all``) route through ``_get``, so they are covered too.

Only ``_get``/``_post`` are overridden because the entire Klear surface is
GET/POST. If a future spec revision adds a PUT/DELETE Klear endpoint, override
the matching base helper here too (otherwise its requests would go out
unauthenticated).
"""

from __future__ import annotations

from typing import Any

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.perps.klear.auth import KlearAuth
from kalshi.resources._base import AsyncResource, SyncResource


def _with_klear_auth(
    auth: KlearAuth, extra_headers: dict[str, str] | None
) -> dict[str, str]:
    """Merge the Klear ``Authorization: Bearer`` header onto ``extra_headers``.

    The Bearer header is set last (and unconditionally) so a caller-supplied
    ``extra_headers`` can never suppress authentication.
    """
    merged = dict(extra_headers) if extra_headers else {}
    merged["Authorization"] = auth.authorization_header()
    return merged


class KlearSyncResource(SyncResource):
    """Sync Klear resource base — transport + Bearer header injection."""

    def __init__(self, transport: SyncTransport, auth: KlearAuth) -> None:
        super().__init__(transport)
        self._klear_auth = auth

    def _with_auth(self, extra_headers: dict[str, str] | None) -> dict[str, str]:
        return _with_klear_auth(self._klear_auth, extra_headers)

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return super()._get(path, params=params, extra_headers=self._with_auth(extra_headers))

    def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return super()._post(
            path, params=params, json=json, extra_headers=self._with_auth(extra_headers)
        )


class KlearAsyncResource(AsyncResource):
    """Async Klear resource base — transport + Bearer header injection."""

    def __init__(self, transport: AsyncTransport, auth: KlearAuth) -> None:
        super().__init__(transport)
        self._klear_auth = auth

    def _with_auth(self, extra_headers: dict[str, str] | None) -> dict[str, str]:
        return _with_klear_auth(self._klear_auth, extra_headers)

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await super()._get(
            path, params=params, extra_headers=self._with_auth(extra_headers)
        )

    async def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await super()._post(
            path, params=params, json=json, extra_headers=self._with_auth(extra_headers)
        )
