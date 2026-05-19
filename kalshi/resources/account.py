"""Account resource — API tier limits for the authenticated user."""

from __future__ import annotations

from kalshi.models.account import AccountApiLimits, AccountEndpointCosts
from kalshi.resources._base import AsyncResource, SyncResource


class AccountResource(SyncResource):
    """Sync account API."""

    def limits(self) -> AccountApiLimits:
        self._require_auth()
        data = self._get("/account/limits")
        return AccountApiLimits.model_validate(data)

    def endpoint_costs(self) -> AccountEndpointCosts:
        """List API v2 endpoints with non-default token costs."""
        self._require_auth()
        data = self._get("/account/endpoint_costs")
        return AccountEndpointCosts.model_validate(data)


class AsyncAccountResource(AsyncResource):
    """Async account API."""

    async def limits(self) -> AccountApiLimits:
        self._require_auth()
        data = await self._get("/account/limits")
        return AccountApiLimits.model_validate(data)

    async def endpoint_costs(self) -> AccountEndpointCosts:
        """List API v2 endpoints with non-default token costs."""
        self._require_auth()
        data = await self._get("/account/endpoint_costs")
        return AccountEndpointCosts.model_validate(data)
