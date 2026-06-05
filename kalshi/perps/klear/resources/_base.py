"""Klear (SCM) resource bases with a session (cookie) auth guard.

Klear authenticates with a session cookie, not RSA-PSS, so the prediction-API
``SyncResource._require_auth`` (which checks the transport's RSA signer) would
always fail. These bases reuse the same transport/HTTP helpers but add
``_require_session()`` — a guard that checks the :class:`KlearAuth` session
holder so an un-logged-in caller gets a clear ``AuthRequiredError`` instead of a
server 401.
"""

from __future__ import annotations

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.errors import AuthRequiredError
from kalshi.perps.klear.auth import KlearAuth
from kalshi.resources._base import AsyncResource, SyncResource


class KlearSyncResource(SyncResource):
    """Sync Klear resource base — transport + Klear session holder."""

    def __init__(self, transport: SyncTransport, auth: KlearAuth) -> None:
        super().__init__(transport)
        self._klear_auth = auth

    def _require_session(self) -> None:
        """Raise ``AuthRequiredError`` if no Klear session has been established."""
        if not self._klear_auth.is_authenticated:
            raise AuthRequiredError(
                "Klear endpoints require an active session. Call "
                "client.auth.log_in(email=..., password=...) first."
            )


class KlearAsyncResource(AsyncResource):
    """Async Klear resource base — transport + Klear session holder."""

    def __init__(self, transport: AsyncTransport, auth: KlearAuth) -> None:
        super().__init__(transport)
        self._klear_auth = auth

    def _require_session(self) -> None:
        """Raise ``AuthRequiredError`` if no Klear session has been established."""
        if not self._klear_auth.is_authenticated:
            raise AuthRequiredError(
                "Klear endpoints require an active session. Call "
                "client.auth.log_in(email=..., password=...) first."
            )
