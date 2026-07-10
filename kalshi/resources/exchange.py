"""Exchange resource — status, schedule, announcements."""

from __future__ import annotations

import builtins
import warnings

from kalshi.models.exchange import (
    Announcement,
    ExchangeStatus,
    Schedule,
    UserDataTimestamp,
)
from kalshi.resources._base import AsyncResource, SyncResource

# Soft-deprecation (spec sync 3.23.0 → 3.24.0): Kalshi removed
# GET /exchange/announcements from the OpenAPI spec. The method is RETAINED
# (not deleted) pending confirmation the removal is permanent — upstream has
# transiently dropped endpoints as publishing glitches before (see the
# CreateOrder/BatchCreateOrders drop reverted in #452). It now emits a
# DeprecationWarning and will 404 against the live API until/unless the endpoint
# returns; a future major release removes it once the removal is confirmed.
_ANNOUNCEMENTS_DEPRECATED = (
    "exchange.announcements() is deprecated: Kalshi removed "
    "GET /exchange/announcements from the OpenAPI spec in v3.24.0, so the live "
    "endpoint now returns 404. The method is retained pending confirmation the "
    "removal is permanent and will be removed in a future major release."
)


class ExchangeResource(SyncResource):
    """Sync exchange API."""

    def status(self, *, extra_headers: dict[str, str] | None = None) -> ExchangeStatus:
        data = self._get("/exchange/status", extra_headers=extra_headers)
        return ExchangeStatus.model_validate(data)

    def schedule(self, *, extra_headers: dict[str, str] | None = None) -> Schedule:
        data = self._get("/exchange/schedule", extra_headers=extra_headers)
        raw = data.get("schedule", data)
        return Schedule.model_validate(raw)

    def announcements(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> builtins.list[Announcement]:
        warnings.warn(_ANNOUNCEMENTS_DEPRECATED, DeprecationWarning, stacklevel=2)
        data = self._get("/exchange/announcements", extra_headers=extra_headers)
        raw = data.get("announcements", [])
        return [Announcement.model_validate(a) for a in raw]

    def user_data_timestamp(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> UserDataTimestamp:
        # Spec has no security block, but the endpoint reports lag on
        # user-scoped routes (balance/orders/fills/positions). Guard
        # client-side so unauth callers get a clear AuthRequiredError
        # instead of a server-side 401.
        self._require_auth()
        data = self._get("/exchange/user_data_timestamp", extra_headers=extra_headers)
        return UserDataTimestamp.model_validate(data)


class AsyncExchangeResource(AsyncResource):
    """Async exchange API."""

    async def status(self, *, extra_headers: dict[str, str] | None = None) -> ExchangeStatus:
        data = await self._get("/exchange/status", extra_headers=extra_headers)
        return ExchangeStatus.model_validate(data)

    async def schedule(self, *, extra_headers: dict[str, str] | None = None) -> Schedule:
        data = await self._get("/exchange/schedule", extra_headers=extra_headers)
        raw = data.get("schedule", data)
        return Schedule.model_validate(raw)

    async def announcements(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> builtins.list[Announcement]:
        warnings.warn(_ANNOUNCEMENTS_DEPRECATED, DeprecationWarning, stacklevel=2)
        data = await self._get("/exchange/announcements", extra_headers=extra_headers)
        raw = data.get("announcements", [])
        return [Announcement.model_validate(a) for a in raw]

    async def user_data_timestamp(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> UserDataTimestamp:
        # See sync note on auth guard (user-scoped endpoint, spec omits security).
        self._require_auth()
        data = await self._get("/exchange/user_data_timestamp", extra_headers=extra_headers)
        return UserDataTimestamp.model_validate(data)
