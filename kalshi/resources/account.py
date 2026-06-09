"""Account resource — API tier limits for the authenticated user."""

from __future__ import annotations

from kalshi.models.account import AccountApiLimits, AccountEndpointCosts
from kalshi.resources._base import AsyncResource, SyncResource


class AccountResource(SyncResource):
    """Sync account API."""

    def limits(self, *, extra_headers: dict[str, str] | None = None) -> AccountApiLimits:
        self._require_auth()
        data = self._get("/account/limits", extra_headers=extra_headers)
        return AccountApiLimits.model_validate(data)

    def endpoint_costs(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> AccountEndpointCosts:
        """List API v2 endpoints with non-default token costs."""
        self._require_auth()
        data = self._get("/account/endpoint_costs", extra_headers=extra_headers)
        return AccountEndpointCosts.model_validate(data)

    def upgrade(self, *, extra_headers: dict[str, str] | None = None) -> None:
        """Request a permanent Advanced API usage-level grant.

        POST ``/account/api_usage_level/upgrade``. Requires that at least one of
        the user's last 100 Predictions orders was API-created (else the server
        returns 403). Returns nothing; inspect the result via :meth:`limits`.
        """
        self._require_auth()
        # Spec defines no requestBody; ``json={}`` forces Content-Type:
        # application/json (httpx omits it for a bodyless POST, which demo
        # rejects) — same workaround as ``subaccounts.create``.
        self._post("/account/api_usage_level/upgrade", json={}, extra_headers=extra_headers)


class AsyncAccountResource(AsyncResource):
    """Async account API."""

    async def limits(self, *, extra_headers: dict[str, str] | None = None) -> AccountApiLimits:
        self._require_auth()
        data = await self._get("/account/limits", extra_headers=extra_headers)
        return AccountApiLimits.model_validate(data)

    async def endpoint_costs(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> AccountEndpointCosts:
        """List API v2 endpoints with non-default token costs."""
        self._require_auth()
        data = await self._get("/account/endpoint_costs", extra_headers=extra_headers)
        return AccountEndpointCosts.model_validate(data)

    async def upgrade(self, *, extra_headers: dict[str, str] | None = None) -> None:
        """Request a permanent Advanced API usage-level grant.

        POST ``/account/api_usage_level/upgrade``. Requires that at least one of
        the user's last 100 Predictions orders was API-created (else the server
        returns 403). Returns nothing; inspect the result via :meth:`limits`.
        """
        self._require_auth()
        # Spec defines no requestBody; ``json={}`` forces Content-Type:
        # application/json (httpx omits it for a bodyless POST, which demo
        # rejects) — same workaround as ``subaccounts.create``.
        await self._post(
            "/account/api_usage_level/upgrade", json={}, extra_headers=extra_headers
        )
