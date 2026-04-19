"""Account resource — API tier limits for the authenticated user."""

from __future__ import annotations

from kalshi.models.account import AccountApiLimits
from kalshi.resources._base import AsyncResource, SyncResource


class AccountResource(SyncResource):
    """Sync account API."""

    def limits(self) -> AccountApiLimits:
        self._require_auth()
        data = self._get("/account/limits")
        return AccountApiLimits.model_validate(data)


class AsyncAccountResource(AsyncResource):
    """Async account API."""

    async def limits(self) -> AccountApiLimits:
        self._require_auth()
        data = await self._get("/account/limits")
        return AccountApiLimits.model_validate(data)
