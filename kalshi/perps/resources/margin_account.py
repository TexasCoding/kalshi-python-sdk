"""Perps margin-account resource — balance, risk, notional risk limit, fee tiers, API limits.

Read-only GET endpoints for the authenticated direct-margin user (#394). All
carry a spec ``security`` block, so each method calls ``_require_auth()`` first
— an unauthenticated caller gets ``AuthRequiredError`` client-side instead of a
server 401. None are paginated (no response carries a cursor), so there are no
``list_all()`` iterators. All retry on 429/502/503/504 (GET).

``api_limits`` (``GET /account/limits/perps``) returns the Perps API tier limits
in the same shape as the prediction API's :class:`~kalshi.models.account.AccountApiLimits`,
so the SDK reuses that model rather than duplicating it.
"""

from __future__ import annotations

from kalshi.models.account import AccountApiLimits
from kalshi.perps.models.margin_account import (
    GetMarginBalanceResponse,
    GetMarginFeeTierRatesResponse,
    GetMarginFeeTiersResponse,
    GetMarginRiskResponse,
    NotionalRiskLimitResponse,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


class MarginAccountResource(SyncResource):
    """Sync perps margin-account API (balance / risk / notional_risk_limit / fee_tiers)."""

    def balance(
        self,
        *,
        compute_available_balance: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginBalanceResponse:
        self._require_auth()
        params = _params(compute_available_balance=compute_available_balance)
        data = self._get("/margin/balance", params=params, extra_headers=extra_headers)
        return GetMarginBalanceResponse.model_validate(data)

    def risk(self, *, extra_headers: dict[str, str] | None = None) -> GetMarginRiskResponse:
        self._require_auth()
        data = self._get("/margin/risk", extra_headers=extra_headers)
        return GetMarginRiskResponse.model_validate(data)

    def notional_risk_limit(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> NotionalRiskLimitResponse:
        self._require_auth()
        data = self._get("/margin/notional_risk_limit", extra_headers=extra_headers)
        return NotionalRiskLimitResponse.model_validate(data)

    def fee_tiers(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTiersResponse:
        self._require_auth()
        data = self._get("/margin/fee_tiers", extra_headers=extra_headers)
        return GetMarginFeeTiersResponse.model_validate(data)

    def fee_tier_rates(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTierRatesResponse:
        """``GET /margin/fee_tier_rates`` — maker/taker rates by fee-schedule tier."""
        self._require_auth()
        data = self._get("/margin/fee_tier_rates", extra_headers=extra_headers)
        return GetMarginFeeTierRatesResponse.model_validate(data)

    def api_limits(self, *, extra_headers: dict[str, str] | None = None) -> AccountApiLimits:
        """Perps (margin) API tier limits for the authenticated user.

        ``GET /account/limits/perps``. Same response shape as the prediction
        API's ``GET /account/limits`` (:class:`~kalshi.models.account.AccountApiLimits`).
        """
        self._require_auth()
        data = self._get("/account/limits/perps", extra_headers=extra_headers)
        return AccountApiLimits.model_validate(data)


class AsyncMarginAccountResource(AsyncResource):
    """Async perps margin-account API (balance / risk / notional_risk_limit / fee_tiers)."""

    async def balance(
        self,
        *,
        compute_available_balance: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginBalanceResponse:
        self._require_auth()
        params = _params(compute_available_balance=compute_available_balance)
        data = await self._get("/margin/balance", params=params, extra_headers=extra_headers)
        return GetMarginBalanceResponse.model_validate(data)

    async def risk(self, *, extra_headers: dict[str, str] | None = None) -> GetMarginRiskResponse:
        self._require_auth()
        data = await self._get("/margin/risk", extra_headers=extra_headers)
        return GetMarginRiskResponse.model_validate(data)

    async def notional_risk_limit(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> NotionalRiskLimitResponse:
        self._require_auth()
        data = await self._get("/margin/notional_risk_limit", extra_headers=extra_headers)
        return NotionalRiskLimitResponse.model_validate(data)

    async def fee_tiers(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTiersResponse:
        self._require_auth()
        data = await self._get("/margin/fee_tiers", extra_headers=extra_headers)
        return GetMarginFeeTiersResponse.model_validate(data)

    async def fee_tier_rates(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTierRatesResponse:
        """Async :meth:`MarginAccountResource.fee_tier_rates`."""
        self._require_auth()
        data = await self._get("/margin/fee_tier_rates", extra_headers=extra_headers)
        return GetMarginFeeTierRatesResponse.model_validate(data)

    async def api_limits(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> AccountApiLimits:
        """Perps (margin) API tier limits for the authenticated user.

        ``GET /account/limits/perps``. Same response shape as the prediction
        API's ``GET /account/limits`` (:class:`~kalshi.models.account.AccountApiLimits`).
        """
        self._require_auth()
        data = await self._get("/account/limits/perps", extra_headers=extra_headers)
        return AccountApiLimits.model_validate(data)
